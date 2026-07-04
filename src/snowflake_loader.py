import snowflake.connector
import logging
import os
from config.config import SNOWFLAKE_CONFIG

logger = logging.getLogger(__name__)


def get_connection():
    """
    Creates and returns a Snowflake connection.
    Credentials come from .env via config.py.
    Never hardcode credentials in code.
    """
    return snowflake.connector.connect(**SNOWFLAKE_CONFIG)


def upload_and_load(local_filepath, filename):
    """
    Two-step process to get data into Snowflake:

    Step 1 — PUT:
    Uploads the local clean CSV into Snowflake's internal stage.
    PUT is Snowflake's proprietary command for uploading files.
    auto_compress=true gzips the file during upload (Snowflake default).
    OVERWRITE=TRUE replaces the file if it already exists in the stage.

    Step 2 — COPY INTO:
    Reads the staged file and loads rows into RAW_TRANSACTIONS.
    ON_ERROR='CONTINUE' means if individual rows fail to parse,
    Snowflake skips them and continues loading the rest.
    This is safer than ON_ERROR='ABORT_STATEMENT' for production.

    Returns: (success: bool, rows_loaded: int)
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # PUT — upload to internal stage
        # Note: file:// prefix is required by Snowflake
        # On Windows use forward slashes or double backslashes
        abs_path = os.path.abspath(local_filepath).replace('\\', '/')
        put_sql = (
            f"PUT 'file://{abs_path}' "
            f"@RETAILX_INTERNAL_STAGE "
            f"OVERWRITE=TRUE "
            f"AUTO_COMPRESS=TRUE"
        )
        logger.info(f"Staging file: {filename}")
        cursor.execute(put_sql)
        put_result = cursor.fetchall()
        logger.info(f"PUT result: {put_result}")

        # COPY INTO — load from stage to table
        copy_sql = f"""
            COPY INTO RETAILX_DB.SALES.RAW_TRANSACTIONS
            FROM @RETAILX_DB.SALES.RETAILX_INTERNAL_STAGE/{filename}.gz
            FILE_FORMAT = (
                TYPE = 'CSV'
                FIELD_OPTIONALLY_ENCLOSED_BY = '"'
                SKIP_HEADER = 1
                NULL_IF = ('NULL', 'null', '')
                EMPTY_FIELD_AS_NULL = TRUE
                DATE_FORMAT = 'YYYY-MM-DD'
                TIMESTAMP_FORMAT = 'AUTO'
            )
            ON_ERROR = 'CONTINUE'
            PURGE = FALSE
        """
        # PURGE = FALSE means the file stays in the stage after loading
        # Set to TRUE in production to avoid stage storage costs
        cursor.execute(copy_sql)
        results = cursor.fetchall()

        rows_loaded = 0
        rows_error = 0
        for row in results:
            rows_loaded += int(row[3]) if row[3] else 0
            rows_error += int(row[4]) if row[4] else 0

        logger.info(
            f"COPY INTO complete: {rows_loaded:,} loaded, "
            f"{rows_error} errors"
        )
        return True, rows_loaded

    except Exception as e:
        logger.error(f"Snowflake load failed for {filename}: {str(e)}")
        return False, 0

    finally:
        cursor.close()
        conn.close()


def file_already_loaded(filename):
    """
    Idempotency check — has this file already been loaded into Snowflake?
    
    Idempotency means: running the same pipeline twice gives the same result.
    Without this check, re-running the pipeline doubles all the data.
    
    We check RAW_TRANSACTIONS for any row with this source_file.
    If count > 0, this file was already processed — skip it.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) FROM RETAILX_DB.SALES.RAW_TRANSACTIONS "
            "WHERE source_file = %s",
            (filename,)
        )
        count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        logger.warning(
            f"Could not check idempotency for {filename}: {e}. "
            f"Will proceed with load."
        )
        return False
    finally:
        cursor.close()
        conn.close()


def insert_pipeline_log(filename, rows_raw, rows_clean,
                         rows_rejected, status, error=''):
    """
    Writes one row to PIPELINE_LOG in Snowflake.
    This is what powers the Pipeline Health Monitor page in Power BI.
    Every pipeline run is permanently recorded here.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO RETAILX_DB.SALES.PIPELINE_LOG
            (source_file, rows_raw, rows_clean, rows_rejected,
             status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (filename, rows_raw, rows_clean, rows_rejected,
               status, error))
        conn.commit()
        logger.info(f"Pipeline log updated for {filename}")
    except Exception as e:
        logger.error(f"Failed to write pipeline log: {e}")
    finally:
        cursor.close()
        conn.close()