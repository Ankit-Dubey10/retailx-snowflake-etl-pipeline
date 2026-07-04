from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType
import logging
import os
import glob
import shutil
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_spark_session():
    """
    Creates a SparkSession in local mode.
    local[*] = use all available CPU cores on this machine.
    In production this config would point to a cluster URL instead.
    The code itself does not change — only this config line.
    """
    spark = (SparkSession.builder
        .appName("RetailX Monthly Sales Pipeline")
        .config("spark.sql.shuffle.partitions", "4")
        # 4 partitions is optimal for small local files
        # On a cluster this would be 200+ for large datasets
        .config("spark.driver.memory", "2g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    logger.info("SparkSession created in local mode")
    return spark


def define_schema():
    """
    Defines the expected schema EXPLICITLY as all StringType.
    
    Why not use inferSchema=True?
    1. inferSchema scans the entire file twice — slower
    2. It can guess wrong on dirty data (e.g. Rs.65000 becomes StringType
       which is correct, but inferSchema might try FloatType and fail)
    3. Explicit schema is self-documenting — anyone reading this knows
       exactly what columns are expected
    
    We use StringType for everything because the data has intentional
    quality issues. We clean first, then cast to correct types.
    Clean first, cast second — always.
    """
    columns = [
        "transaction_id", "date", "month", "year", "region",
        "salesperson_id", "salesperson_name", "product_category",
        "product_name", "customer_segment", "customer_id",
        "units_sold", "unit_price", "discount_pct", "gross_revenue",
        "discount_amount", "net_revenue", "cost_per_unit",
        "total_cost", "gross_profit", "profit_margin_pct",
        "monthly_target", "return_flag", "payment_method"
    ]
    return StructType([
        StructField(col, StringType(), True) for col in columns
    ])


def validate_schema(df, filename):
    """
    Checks that incoming file has exactly the expected columns.
    Raises ValueError immediately if schema does not match.
    This is the first line of defense — a file with wrong columns
    should never proceed further down the pipeline.
    """
    expected = set(define_schema().fieldNames())
    actual = set(df.columns)
    missing = expected - actual
    extra = actual - expected

    if missing:
        raise ValueError(
            f"Schema validation FAILED for {filename}. "
            f"Missing columns: {missing}"
        )
    if extra:
        logger.warning(
            f"Extra columns found in {filename}: {extra}. "
            f"These will be ignored."
        )
    logger.info(f"Schema validation PASSED for {filename}")


def remove_duplicates(df):
    """
    Drops exact duplicate rows using dropDuplicates().
    PySpark's dropDuplicates() runs in parallel across partitions.
    In pandas this would be df.drop_duplicates().
    The API is similar but the execution is distributed.
    """
    before = df.count()
    df = df.dropDuplicates()
    after = df.count()
    removed = before - after
    if removed > 0:
        logger.info(f"Removed {removed:,} duplicate rows")
    return df, removed


def fix_date_column(df):
    """
    Converts date from DD-MM-YYYY string to proper DateType.

    to_date() with format='dd-MM-yyyy' tells Spark exactly
    how to parse the string. errors='coerce' equivalent in Spark
    is the default behaviour — unparseable dates become null (NaT).
    We then drop rows where date parsing failed.

    We also create yearmonth (YYYY-MM format) here because it is
    needed for all trend analysis in Power BI.
    """
    df = df.withColumn(
        "txn_date",
        F.to_date(F.col("date"), "dd-MM-yyyy")
    )
    bad_dates = df.filter(F.col("txn_date").isNull()).count()
    if bad_dates > 0:
        logger.warning(f"Dropping {bad_dates} rows with unparseable dates")
    df = df.filter(F.col("txn_date").isNotNull())

    # YYYY-MM format for trend chart x-axis
    df = df.withColumn(
        "yearmonth",
        F.date_format(F.col("txn_date"), "yyyy-MM")
    )

    # Drop the original messy date string — not needed anymore
    df = df.drop("date")
    return df, bad_dates


def standardize_region(df):
    """
    Fixes inconsistent region casing.
    initcap() = capitalise first letter of each word.
    north -> North, SOUTH -> South, EAST -> East, west -> West.
    This is equivalent to str.title() in Python/pandas.
    """
    df = df.withColumn("region", F.initcap(F.col("region")))
    return df


def clean_unit_price(df):
    """
    Removes currency symbols from unit_price and converts to float.

    regexp_replace(column, pattern, replacement):
    Removes every character except digits and decimal point.
    - replacing with '' effectively strips Rs., £, $, spaces, etc.

    cast("float") then converts the cleaned string to a number.
    Rows where conversion still fails (truly corrupt) become null
    and are dropped.
    """
    df = df.withColumn(
        "unit_price",
        F.regexp_replace(
            F.col("unit_price"),
            r"^Rs\.",
            ""
        )
    )

    df = df.withColumn(
        "unit_price",
        F.col("unit_price").cast("float")
    )
    corrupt = df.filter(F.col("unit_price").isNull()).count()
    if corrupt > 0:
        logger.warning(f"Dropping {corrupt} rows with unrecoverable unit_price")
    df = df.filter(F.col("unit_price").isNotNull())
    return df, corrupt


def fill_null_product_names(df):
    """
    Fills null product_name with '[Category] - Unknown Product'.
    
    coalesce() returns the first non-null value from its arguments.
    We pass the product_name first, then a fallback string.
    If product_name is not null, coalesce returns it unchanged.
    If product_name IS null, coalesce returns the fallback.

    We do NOT drop null product names — the row is still useful
    for revenue analysis even without a specific product name.
    The category alone tells us enough.
    """
    df = df.withColumn(
        "product_name",
        F.coalesce(
            F.col("product_name"),
            F.concat(
                F.col("product_category"),
                F.lit(" - Unknown Product")
            )
        )
    )
    return df


def cast_and_validate_numeric_columns(df):
    """
    Casts all remaining string columns to their correct types
    AND applies business rule validation.

    ORDER MATTERS:
    1. Clean strings first (done above)
    2. Cast to correct types (done here)
    3. Validate business rules (done here too)

    Business rules applied:
    - units_sold: take abs() to fix negative values (data entry errors)
      We do not DROP negative units — we CORRECT them, because the
      transaction happened. The sign was just entered wrong.
    - unit_price > 0: a price of zero or negative is physically impossible
    - discount_pct between 0 and 100: impossible otherwise

    Why abs() for units instead of dropping?
    Dropping means losing revenue data. Taking the absolute value
    preserves the transaction while fixing the obvious error.
    """
    df = (df
        .withColumn("month",
            F.col("month").cast("integer"))
        .withColumn("year",
            F.col("year").cast("integer"))
        .withColumn("units_sold",
            F.abs(F.col("units_sold").cast("integer")))
        .withColumn("discount_pct",
            F.col("discount_pct").cast("float"))
        .withColumn("gross_revenue",
            F.col("gross_revenue").cast("float"))
        .withColumn("discount_amount",
            F.col("discount_amount").cast("float"))
        .withColumn("net_revenue",
            F.col("net_revenue").cast("float"))
        .withColumn("cost_per_unit",
            F.col("cost_per_unit").cast("float"))
        .withColumn("total_cost",
            F.col("total_cost").cast("float"))
        .withColumn("gross_profit",
            F.col("gross_profit").cast("float"))
        .withColumn("profit_margin_pct",
            F.col("profit_margin_pct").cast("float"))
        .withColumn("monthly_target",
            F.col("monthly_target").cast("float"))
        .withColumn("return_flag",
            F.col("return_flag").cast("boolean"))
    )

    # Business rule: drop rows with impossible values
    before = df.count()
    df = df.filter(
        (F.col("unit_price") > 0) &
        (F.col("discount_pct") >= 0) &
        (F.col("discount_pct") <= 100) &
        (F.col("units_sold").isNotNull())
    )
    dropped = before - df.count()
    if dropped > 0:
        logger.warning(
            f"Business rule validation dropped {dropped} rows"
        )
    return df


def add_metadata_columns(df, filename):
    """
    Adds two audit columns to every row.

    source_file: which monthly CSV this row came from.
    This lets us trace every row back to its origin file.
    Used by the Pipeline Health Monitor page in Power BI.

    loaded_at: timestamp of when this pipeline run processed this row.
    This lets us see exactly when each month's data entered the system.

    F.lit() creates a literal constant column —
    same value for every row in the dataframe.
    """
    df = (df
        .withColumn("source_file", F.lit(filename))
        .withColumn("loaded_at",
            F.lit(datetime.now().isoformat()).cast("timestamp"))
    )
    return df


def select_final_columns(df):
    """
    Selects and orders columns for the output file.
    Explicit selection documents the output schema clearly.
    Drops 'date' (already dropped) and any intermediate columns.
    """
    return df.select(
        "transaction_id", "txn_date", "month", "year", "yearmonth",
        "region", "salesperson_id", "salesperson_name",
        "product_category", "product_name", "customer_segment",
        "customer_id", "units_sold", "unit_price", "discount_pct",
        "gross_revenue", "discount_amount", "net_revenue",
        "cost_per_unit", "total_cost", "gross_profit",
        "profit_margin_pct", "monthly_target", "return_flag",
        "payment_method", "source_file", "loaded_at"
    )


def transform_monthly_file(filepath, output_dir):
    """
    Master orchestration function for one monthly file.
    Runs all cleaning steps in the correct order.
    Returns a quality report dictionary for logging.
    """
    filename = os.path.basename(filepath)
    logger.info(f"\n{'='*50}")
    logger.info(f"PROCESSING: {filename}")
    logger.info(f"{'='*50}")

    spark = create_spark_session()
    report = {'filename': filename}

    try:
        # LOAD
        df = spark.read.csv(
            filepath,
            header=True,
            schema=define_schema()
        )
        raw_count = df.count()
        report['rows_raw'] = raw_count
        logger.info(f"Loaded {raw_count:,} raw rows")

        # VALIDATE SCHEMA
        validate_schema(df, filename)

        # CLEAN (order matters — schema before types, types before rules)
        df, dupes = remove_duplicates(df)
        df, bad_dates = fix_date_column(df)
        df = standardize_region(df)
        df, corrupt_prices = clean_unit_price(df)
        df = fill_null_product_names(df)
        df = cast_and_validate_numeric_columns(df)
        df = add_metadata_columns(df, filename)
        df = select_final_columns(df)

        # WRITE
        # coalesce(1) merges all Spark partitions into ONE output file
        # This is correct for small monthly files going to Snowflake
        # For large files in production you would skip coalesce()
        # and let Snowflake handle multiple part files
        output_path = os.path.join(output_dir, filename)
        temp_path = output_path + "_spark_temp"

        (df.coalesce(1)
           .write
           .mode("overwrite")
           .option("header", "true")
           .csv(temp_path)
        )

        # PySpark writes to a folder with part-*.csv files inside
        # We move the actual CSV to the expected filename
        part_files = glob.glob(f"{temp_path}/part-*.csv")
        if part_files:
            shutil.copy(part_files[0], output_path)
            shutil.rmtree(temp_path)
        else:
            raise FileNotFoundError(
                f"PySpark output not found in {temp_path}"
            )

        clean_count = df.count()
        report.update({
            'rows_clean': clean_count,
            'rows_rejected': raw_count - clean_count,
            'status': 'SUCCESS',
            'details': {
                'duplicates_removed': dupes,
                'bad_dates_dropped': bad_dates,
                'corrupt_prices_dropped': corrupt_prices,
            }
        })

        logger.info(f"SUCCESS: {filename}")
        logger.info(f"  Raw: {raw_count:,} → Clean: {clean_count:,}")
        logger.info(
            f"  Rejected: {raw_count - clean_count:,} rows"
        )

    except Exception as e:
        report['status'] = 'FAILED'
        report['error'] = str(e)
        logger.error(f"FAILED: {filename} — {str(e)}")
        raise

    finally:
        spark.stop()

    return report