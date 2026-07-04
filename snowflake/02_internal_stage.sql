USE WAREHOUSE RETAILX_WH;
USE DATABASE RETAILX_DB;
USE SCHEMA SALES;

-- An internal stage is storage that lives INSIDE Snowflake
-- Files uploaded here are held by Snowflake temporarily
-- until COPY INTO moves them into a proper table
-- No external cloud account needed — Snowflake manages all storage
CREATE STAGE IF NOT EXISTS RETAILX_INTERNAL_STAGE
    FILE_FORMAT = (
        TYPE = 'CSV'
        FIELD_OPTIONALLY_ENCLOSED_BY = '"'
        SKIP_HEADER = 1
        NULL_IF = ('NULL', 'null', '')
        EMPTY_FIELD_AS_NULL = TRUE
        DATE_FORMAT = 'YYYY-MM-DD'
        TIMESTAMP_FORMAT = 'AUTO'
    );

-- Verify it was created
LIST @RETAILX_INTERNAL_STAGE;

-- Test manually: after you PUT a file from Python
-- run this to confirm it appears
-- LIST @RETAILX_INTERNAL_STAGE PATTERN='.*2022_01.*';