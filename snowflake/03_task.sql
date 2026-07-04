USE WAREHOUSE RETAILX_WH;
USE DATABASE RETAILX_DB;
USE SCHEMA SALES;

-- ============================================
-- SNOWFLAKE TASK: REFRESH ANALYTICS
-- Runs every day at 6am UTC (11:30am IST)
-- Rebuilds MONTHLY_ANALYTICS from scratch
-- after new monthly data lands in RAW_TRANSACTIONS
--
-- Why CREATE OR REPLACE inside the task?
-- This ensures the table is always in sync with
-- the query definition. If we add/remove columns
-- later, the task picks up the change automatically.
--
-- Why not CREATE TABLE separately first?
-- The task itself handles table creation on first
-- run. No need for a separate CREATE TABLE block.
-- ============================================

CREATE OR REPLACE TASK REFRESH_ANALYTICS_TASK
    WAREHOUSE = RETAILX_WH
    SCHEDULE = 'USING CRON 0 6 * * * UTC'
    COMMENT = 'Daily refresh of MONTHLY_ANALYTICS after new data loads'
AS
CREATE OR REPLACE TABLE RETAILX_DB.SALES.MONTHLY_ANALYTICS AS
SELECT
    year,
    month,
    yearmonth,
    region,
    product_category,
    customer_segment,
    COUNT(DISTINCT transaction_id)              AS total_transactions,
    SUM(units_sold)                             AS total_units,
    ROUND(SUM(gross_revenue), 2)                AS total_gross_revenue,
    ROUND(SUM(discount_amount), 2)              AS total_discount,
    ROUND(SUM(net_revenue), 2)                  AS total_net_revenue,
    ROUND(SUM(gross_profit), 2)                 AS total_profit,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin_pct,
    SUM(CASE WHEN return_flag = TRUE
        THEN 1 ELSE 0 END)                      AS return_count,
    COUNT(DISTINCT salesperson_id)              AS active_salespeople
FROM RAW_TRANSACTIONS
WHERE unit_price > 0
GROUP BY year, month, yearmonth, region,
         product_category, customer_segment;

-- Resume the task so it runs on schedule
ALTER TASK REFRESH_ANALYTICS_TASK RESUME;

-- Verify task is active and scheduled correctly
SHOW TASKS;

-- ============================================
-- DO NOT run EXECUTE TASK yet.
-- Run this only AFTER all 36 files are loaded.
--
-- EXECUTE TASK REFRESH_ANALYTICS_TASK;
--
-- Then verify with:
-- SELECT COUNT(*) FROM MONTHLY_ANALYTICS;
-- SELECT * FROM MONTHLY_ANALYTICS LIMIT 5;
-- ============================================