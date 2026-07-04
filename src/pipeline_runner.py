import os
import sys
import logging
from datetime import datetime

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from src.pyspark_transform import transform_monthly_file
from src.snowflake_loader import (
    upload_and_load, file_already_loaded, insert_pipeline_log
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)

MONTHLY_DROPS = 'data/monthly_drops'
PROCESSED_DIR = 'data/processed'
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs('logs', exist_ok=True)


def run_pipeline(force=False):
    """
    Orchestrates the full pipeline for all pending monthly files.

    For each CSV found in data/monthly_drops/:
      1. Check if already loaded (idempotency guard)
      2. Transform with PySpark
      3. Upload to Snowflake internal stage (PUT)
      4. Load into RAW_TRANSACTIONS (COPY INTO)
      5. Write result to PIPELINE_LOG

    force=True: reprocess ALL files regardless of load history.
                Use for the initial bulk load of all 36 months.
    force=False: only process files not yet in Snowflake.
                 Use for all subsequent monthly runs.
    """
    logger.info("=" * 60)
    logger.info("RetailX PySpark + Snowflake Pipeline")
    logger.info(f"Mode: {'FORCE REPROCESS ALL' if force else 'INCREMENTAL'}")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    csv_files = sorted(
        f for f in os.listdir(MONTHLY_DROPS) if f.endswith('.csv')
    )
    
    if not csv_files:
        logger.warning("No CSV files found in data/monthly_drops/")
        return

    logger.info(f"Found {len(csv_files)} files to evaluate")

    processed = skipped = failed = 0

    for filename in csv_files:
        filepath = os.path.join(MONTHLY_DROPS, filename)

        # IDEMPOTENCY CHECK
        if not force and file_already_loaded(filename):
            logger.info(f"Skipping (already in Snowflake): {filename}")
            skipped += 1
            continue

        try:
            # STEP 1: PySpark transformation
            report = transform_monthly_file(filepath, PROCESSED_DIR)
            clean_path = os.path.join(PROCESSED_DIR, filename)

            # STEP 2: Upload to Snowflake + load
            success, rows_loaded = upload_and_load(clean_path, filename)

            if success:
                insert_pipeline_log(
                    filename=filename,
                    rows_raw=report.get('rows_raw', 0),
                    rows_clean=report.get('rows_clean', 0),
                    rows_rejected=report.get('rows_rejected', 0),
                    status='SUCCESS'
                )
                processed += 1
                logger.info(f"COMPLETE: {filename} ✓")
            else:
                insert_pipeline_log(
                    filename, 0, 0, 0,
                    'LOAD_FAILED', 'Snowflake load returned False'
                )
                failed += 1

        except Exception as e:
            insert_pipeline_log(
                filename, 0, 0, 0, 'FAILED', str(e)
            )
            logger.error(f"FAILED: {filename} — {str(e)}")
            failed += 1

    logger.info("=" * 60)
    logger.info(
        f"Pipeline complete — "
        f"Processed: {processed} | "
        f"Skipped: {skipped} | "
        f"Failed: {failed}"
    )
    logger.info("=" * 60)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='RetailX monthly sales pipeline'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Reprocess all files, ignoring prior load history'
    )
    args = parser.parse_args()
    run_pipeline(force=args.force)