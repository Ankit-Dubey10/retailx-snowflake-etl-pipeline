-- Step 1: Create a virtual warehouse (the compute engine)
-- X-SMALL is the smallest and cheapest size
-- AUTO_SUSPEND = 60 means it shuts off after 60 seconds of inactivity
-- AUTO_RESUME = TRUE means it wakes up automatically when needed
-- INITIALLY_SUSPENDED = TRUE means it starts off to save credits
CREATE WAREHOUSE IF NOT EXISTS RETAILX_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

-- Step 2: Create the database and schema
CREATE DATABASE IF NOT EXISTS RETAILX_DB;
CREATE SCHEMA IF NOT EXISTS RETAILX_DB.SALES;

-- Step 3: Set context so all subsequent commands 
-- know which warehouse, database, and schema to use
USE WAREHOUSE RETAILX_WH;
USE DATABASE RETAILX_DB;
USE SCHEMA SALES;

-- Step 4: Create RAW_TRANSACTIONS table
-- This receives every row from every monthly file via COPY INTO
-- All columns start as VARCHAR or basic types because
-- PySpark handles type validation before data reaches here
CREATE TABLE IF NOT EXISTS RAW_TRANSACTIONS (
    transaction_id      VARCHAR(30),
    txn_date            DATE,
    month               INTEGER,
    year                INTEGER,
    yearmonth           VARCHAR(8),
    region              VARCHAR(20),
    salesperson_id      VARCHAR(10),
    salesperson_name    VARCHAR(100),
    product_category    VARCHAR(50),
    product_name        VARCHAR(100),
    customer_segment    VARCHAR(10),
    customer_id         VARCHAR(15),
    units_sold          INTEGER,
    unit_price          FLOAT,
    discount_pct        FLOAT,
    gross_revenue       FLOAT,
    discount_amount     FLOAT,
    net_revenue         FLOAT,
    cost_per_unit       FLOAT,
    total_cost          FLOAT,
    gross_profit        FLOAT,
    profit_margin_pct   FLOAT,
    monthly_target      FLOAT,
    return_flag         BOOLEAN,
    payment_method      VARCHAR(20),
    source_file         VARCHAR(200),
    loaded_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Step 5: Create pipeline log table
-- Every pipeline run writes one row here
-- This powers the Pipeline Health Monitor page in Power BI
CREATE TABLE IF NOT EXISTS PIPELINE_LOG (
    log_id          INTEGER AUTOINCREMENT PRIMARY KEY,
    run_timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    source_file     VARCHAR(200),
    rows_raw        INTEGER,
    rows_clean      INTEGER,
    rows_rejected   INTEGER,
    status          VARCHAR(20),
    error_message   VARCHAR(500)
);

-- Verify both tables were created
SHOW TABLES;