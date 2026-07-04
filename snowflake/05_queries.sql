USE WAREHOUSE RETAILX_WH;
USE DATABASE RETAILX_DB;
USE SCHEMA SALES;

-- ============================================
-- QUERY 1: Monthly Revenue vs Target + MoM Growth
-- Tests: CTE, LAG window function, NULLIF
-- ============================================

WITH monthly AS (
    SELECT
        year,
        month,
        yearmonth,
        SUM(net_revenue)                        AS revenue,
        AVG(monthly_target) *
            COUNT(DISTINCT salesperson_id)      AS total_target
    FROM VW_CLEAN_TRANSACTIONS
    WHERE return_flag = FALSE
    GROUP BY year, month, yearmonth
)
SELECT
    yearmonth,
    ROUND(revenue, 2)                           AS revenue,
    ROUND(total_target, 2)                      AS total_target,
    ROUND(revenue /
        NULLIF(total_target, 0) * 100, 1)       AS target_ach_pct,
    ROUND(LAG(revenue)
        OVER (ORDER BY year, month), 2)         AS prev_month_revenue,
    ROUND(
        (revenue -
            LAG(revenue) OVER (ORDER BY year, month)) /
        NULLIF(
            LAG(revenue) OVER (ORDER BY year, month), 0)
        * 100, 1)                               AS mom_growth_pct
FROM monthly
ORDER BY year, month;

-- ============================================
-- QUERY 2: Regional Performance with RANK
-- Tests: RANK window function, PARTITION BY
-- ============================================

SELECT
    region,
    year,
    ROUND(SUM(net_revenue), 2)                  AS annual_revenue,
    ROUND(SUM(gross_profit), 2)                 AS annual_profit,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin,
    COUNT(DISTINCT salesperson_id)              AS headcount,
    ROUND(SUM(net_revenue) /
        COUNT(DISTINCT salesperson_id), 2)      AS revenue_per_head,
    RANK() OVER (
        PARTITION BY year
        ORDER BY SUM(net_revenue) DESC)         AS revenue_rank
FROM VW_CLEAN_TRANSACTIONS
GROUP BY region, year
ORDER BY year, revenue_rank;

-- ============================================
-- QUERY 3: Salesperson Leaderboard 2024
-- Tests: CTE, CASE WHEN, RANK
-- ============================================

WITH sp AS (
    SELECT
        salesperson_id,
        salesperson_name,
        region,
        SUM(net_revenue)                        AS annual_revenue,
        AVG(monthly_target) * 12               AS annual_target,
        ROUND(AVG(profit_margin_pct), 2)        AS avg_margin,
        COUNT(DISTINCT customer_id)             AS unique_customers
    FROM VW_CLEAN_TRANSACTIONS
    WHERE year = 2024
    GROUP BY salesperson_id, salesperson_name, region
)
SELECT
    RANK() OVER (
        ORDER BY annual_revenue DESC)           AS revenue_rank,
    salesperson_id,
    salesperson_name,
    region,
    ROUND(annual_revenue, 2)                    AS annual_revenue,
    ROUND(annual_target, 2)                     AS annual_target,
    ROUND(annual_revenue /
        NULLIF(annual_target, 0) * 100, 1)      AS target_ach_pct,
    avg_margin,
    unique_customers,
    CASE
        WHEN annual_revenue /
             NULLIF(annual_target, 0) >= 1.0   THEN 'On Target'
        WHEN annual_revenue /
             NULLIF(annual_target, 0) >= 0.8   THEN 'Near Target'
        ELSE 'Below Target'
    END                                         AS performance_band
FROM sp
ORDER BY revenue_rank;

-- ============================================
-- QUERY 4: Discount Impact Analysis
-- Tests: GROUP BY, aggregation, derived metrics
-- ============================================

SELECT
    discount_pct,
    COUNT(*)                                    AS transaction_count,
    ROUND(SUM(net_revenue), 2)                  AS total_revenue,
    ROUND(SUM(discount_amount), 2)              AS revenue_sacrificed,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin,
    ROUND(
        SUM(discount_amount) /
        NULLIF(SUM(gross_revenue), 0) * 100, 2) AS effective_discount_rate
FROM VW_CLEAN_TRANSACTIONS
WHERE return_flag = FALSE
GROUP BY discount_pct
ORDER BY discount_pct;

-- ============================================
-- QUERY 5: Product Category YoY Growth
-- Tests: LAG with PARTITION BY on category
-- ============================================

SELECT
    product_category,
    year,
    ROUND(SUM(net_revenue), 2)                  AS revenue,
    ROUND(SUM(gross_profit), 2)                 AS profit,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin,
    ROUND(
        LAG(SUM(net_revenue)) OVER (
            PARTITION BY product_category
            ORDER BY year), 2)                  AS prev_year_revenue,
    ROUND(
        (SUM(net_revenue) -
            LAG(SUM(net_revenue)) OVER (
                PARTITION BY product_category
                ORDER BY year)) /
        NULLIF(
            LAG(SUM(net_revenue)) OVER (
                PARTITION BY product_category
                ORDER BY year), 0)
        * 100, 1)                               AS yoy_growth_pct
FROM VW_CLEAN_TRANSACTIONS
GROUP BY product_category, year
ORDER BY product_category, year;

-- ============================================
-- QUERY 6: B2B vs B2C Monthly Trend
-- Tests: GROUP BY on multiple dimensions
-- ============================================

SELECT
    yearmonth,
    year,
    month,
    customer_segment,
    ROUND(SUM(net_revenue), 2)                  AS revenue,
    ROUND(AVG(profit_margin_pct), 2)            AS avg_margin,
    COUNT(DISTINCT customer_id)                 AS unique_customers,
    ROUND(SUM(net_revenue) /
        NULLIF(COUNT(DISTINCT transaction_id),
            0), 2)                              AS avg_transaction_value
FROM VW_CLEAN_TRANSACTIONS
GROUP BY yearmonth, year, month, customer_segment
ORDER BY year, month, customer_segment;

-- ============================================
-- QUERY 7: Return Rate by Category and Region
-- Tests: CASE WHEN aggregation, complex GROUP BY
-- ============================================

SELECT
    product_category,
    region,
    COUNT(*)                                    AS total_transactions,
    SUM(CASE WHEN return_flag
        THEN 1 ELSE 0 END)                      AS returns,
    ROUND(
        SUM(CASE WHEN return_flag
            THEN 1 ELSE 0 END) /
        NULLIF(COUNT(*), 0) * 100, 2)           AS return_rate_pct,
    ROUND(SUM(
        CASE WHEN return_flag
            THEN ABS(net_revenue)
            ELSE 0 END), 2)                     AS revenue_lost_to_returns
FROM VW_CLEAN_TRANSACTIONS
GROUP BY product_category, region
ORDER BY return_rate_pct DESC;

-- ============================================
-- QUERY 8: Rolling 3-Month Revenue by Region
-- Tests: ROWS BETWEEN window frame
-- ============================================

WITH monthly_region AS (
    SELECT
        year,
        month,
        yearmonth,
        region,
        SUM(net_revenue)                        AS monthly_revenue
    FROM VW_CLEAN_TRANSACTIONS
    GROUP BY year, month, yearmonth, region
)
SELECT
    yearmonth,
    region,
    ROUND(monthly_revenue, 2)                   AS monthly_revenue,
    ROUND(AVG(monthly_revenue) OVER (
        PARTITION BY region
        ORDER BY year, month
        ROWS BETWEEN 2 PRECEDING
             AND CURRENT ROW), 2)               AS rolling_3m_avg
FROM monthly_region
ORDER BY region, year, month;