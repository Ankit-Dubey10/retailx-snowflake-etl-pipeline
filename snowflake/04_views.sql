USE WAREHOUSE RETAILX_WH;
USE DATABASE RETAILX_DB;
USE SCHEMA SALES;

-- ============================================
-- VIEW 1: CLEAN TRANSACTIONS
-- Primary view — Power BI reads this directly
-- Applies final data quality guards on top of
-- RAW_TRANSACTIONS
-- ============================================

CREATE OR REPLACE VIEW VW_CLEAN_TRANSACTIONS AS
SELECT
    transaction_id,
    txn_date,
    -- txn_date is already DATE type in RAW_TRANSACTIONS
    -- no need to cast again — just use it directly
    month,
    year,
    yearmonth,
    INITCAP(region)                             AS region,
    salesperson_id,
    salesperson_name,
    product_category,
    COALESCE(product_name,
        product_category || ' - Unknown')       AS product_name,
    customer_segment,
    customer_id,
    ABS(units_sold)                             AS units_sold,
    unit_price,
    discount_pct,
    gross_revenue,
    discount_amount,
    net_revenue,
    total_cost,
    gross_profit,
    profit_margin_pct,
    monthly_target,
    return_flag,
    payment_method,
    source_file,
    loaded_at
FROM RAW_TRANSACTIONS
WHERE unit_price > 0;

-- ============================================
-- VIEW 2: MONTHLY SUMMARY
-- Pre-aggregated monthly KPIs
-- Powers revenue trend, profit trend,
-- and time-series charts in Power BI
-- without re-aggregating the full table
-- on every dashboard refresh
-- ============================================

CREATE OR REPLACE VIEW VW_MONTHLY_SUMMARY AS
SELECT
    year,
    month,
    yearmonth,
    SUM(net_revenue)                            AS total_revenue,
    SUM(gross_profit)                           AS total_profit,
    SUM(units_sold)                             AS total_units,
    COUNT(DISTINCT transaction_id)              AS total_orders,
    COUNT(DISTINCT customer_id)                 AS unique_customers,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin
FROM VW_CLEAN_TRANSACTIONS
GROUP BY year, month, yearmonth;

-- ============================================
-- VIEW 3: SALESPERSON PERFORMANCE
-- One row per salesperson per month
-- Used for leaderboard and target tracking
-- in Power BI
-- ============================================

CREATE OR REPLACE VIEW VW_SALESPERSON_PERFORMANCE AS
SELECT
    year,
    month,
    yearmonth,
    region,
    salesperson_id,
    salesperson_name,
    SUM(net_revenue)                            AS total_revenue,
    AVG(monthly_target)                         AS monthly_target,
    ROUND(
        SUM(net_revenue) /
        NULLIF(AVG(monthly_target), 0)
        * 100, 1)                               AS target_achievement_pct,
    ROUND(SUM(gross_profit), 2)                 AS total_profit,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin,
    COUNT(DISTINCT transaction_id)              AS total_transactions,
    COUNT(DISTINCT customer_id)                 AS unique_customers,
    SUM(CASE WHEN return_flag = TRUE
        THEN 1 ELSE 0 END)                      AS return_count,
    CASE
        WHEN SUM(net_revenue) /
             NULLIF(AVG(monthly_target), 0)
             >= 1.0                             THEN 'On Target'
        WHEN SUM(net_revenue) /
             NULLIF(AVG(monthly_target), 0)
             >= 0.8                             THEN 'Near Target'
        ELSE 'Below Target'
    END                                         AS performance_band
FROM VW_CLEAN_TRANSACTIONS
GROUP BY year, month, yearmonth, region,
         salesperson_id, salesperson_name;

-- ============================================
-- VIEW 4: PIPELINE LOG
-- Powers the Pipeline Health Monitor page
-- NO ORDER BY inside the view —
-- the consumer decides sort order
-- ============================================

CREATE OR REPLACE VIEW VW_PIPELINE_LOG AS
SELECT
    log_id,
    run_timestamp,
    source_file,
    rows_raw,
    rows_clean,
    rows_rejected,
    ROUND(
        rows_rejected::FLOAT /
        NULLIF(rows_raw, 0) * 100, 2)           AS rejection_rate_pct,
    status,
    error_message,
    DATEDIFF('second',
        LAG(run_timestamp)
            OVER (ORDER BY run_timestamp),
        run_timestamp)                          AS seconds_since_last_run
FROM PIPELINE_LOG;

-- ============================================
-- VERIFY ALL 4 VIEWS
-- Run these after creating the views to confirm
-- everything is working correctly
-- ============================================

SELECT COUNT(*) FROM VW_CLEAN_TRANSACTIONS;

SELECT COUNT(*) FROM VW_SALESPERSON_PERFORMANCE;

SELECT COUNT(*) FROM VW_MONTHLY_SUMMARY;

SELECT *
FROM VW_PIPELINE_LOG
ORDER BY run_timestamp DESC
LIMIT 5;