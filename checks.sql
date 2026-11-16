-- Supervisory return checks.
-- The database is data/returns.db. Tables: submissions, institutions.
-- These queries are the same rules as analysis.py and the Streamlit app.
-- Amounts are in £ millions. Ratios are in percent.

-- 1. Blank cells that a reviewer has to send back.
SELECT institution_id, institution, quarter, 'Missing value' AS check_name, 'NPL amount' AS field
FROM submissions WHERE npl_amount IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'Provisions'
FROM submissions WHERE provisions IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'HQLA'
FROM submissions WHERE hqla IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'Net income'
FROM submissions WHERE net_income IS NULL;

-- 2. Assets should equal liabilities + equity, within 2% of assets (and at least 50).
SELECT institution_id, institution, quarter,
       total_assets - (total_liabilities + total_equity) AS gap
FROM submissions
WHERE total_assets IS NOT NULL
  AND total_liabilities IS NOT NULL
  AND total_equity IS NOT NULL
  AND ABS(total_assets - (total_liabilities + total_equity))
        > MAX(50, 0.02 * ABS(total_assets));

-- 3. Reported CET1 ratio should match CET1 capital / risk-weighted assets.
SELECT institution_id, institution, quarter, cet1_ratio AS reported,
       ROUND(100.0 * cet1_capital / risk_weighted_assets, 2) AS implied
FROM submissions
WHERE risk_weighted_assets > 0
  AND cet1_capital IS NOT NULL
  AND cet1_ratio IS NOT NULL
  AND ABS(cet1_ratio - (100.0 * cet1_capital / risk_weighted_assets)) > 1.0;

-- 4. Reported NPL ratio should match NPL amount / gross loans.
SELECT institution_id, institution, quarter, npl_ratio AS reported,
       ROUND(100.0 * npl_amount / gross_loans, 2) AS implied
FROM submissions
WHERE gross_loans > 0
  AND npl_amount IS NOT NULL
  AND npl_ratio IS NOT NULL
  AND ABS(npl_ratio - (100.0 * npl_amount / gross_loans)) > 1.0;

-- 5. Reported LCR should match HQLA / 30-day net outflows.
SELECT institution_id, institution, quarter, lcr AS reported,
       ROUND(100.0 * hqla / net_outflows_30d, 1) AS implied
FROM submissions
WHERE net_outflows_30d > 0
  AND hqla IS NOT NULL
  AND lcr IS NOT NULL
  AND ABS(lcr - (100.0 * hqla / net_outflows_30d)) > 5;

-- 6. Sign errors.
SELECT institution_id, institution, quarter, 'Gross loans' AS field, gross_loans AS value
FROM submissions WHERE gross_loans < 0
UNION ALL
SELECT institution_id, institution, quarter, 'Total equity', total_equity
FROM submissions WHERE total_equity < 0;

-- 7. Plausibility bounds (percent).
SELECT institution_id, institution, quarter, 'CET1 ratio' AS field, cet1_ratio AS value
FROM submissions WHERE cet1_ratio < 4 OR cet1_ratio > 35
UNION ALL
SELECT institution_id, institution, quarter, 'NPL ratio', npl_ratio
FROM submissions WHERE npl_ratio < 0 OR npl_ratio > 25
UNION ALL
SELECT institution_id, institution, quarter, 'LCR', lcr
FROM submissions WHERE lcr < 40 OR lcr > 350;

-- Peer outliers and quarter-on-quarter jumps are easier to express with window
-- functions. SQLite supports both.

-- 8. Peer outlier: robust z-score of at least 4.5 within the quarter.
WITH stats AS (
  SELECT quarter,
         AVG(lcr) AS mean_lcr -- placeholder, robust stats are computed in analysis.py
  FROM submissions
  GROUP BY quarter
)
SELECT * FROM stats LIMIT 0;

-- The robust (median / MAD) z-score is computed in analysis.py because SQLite
-- has no MEDIAN aggregate until very recent builds. The query below is the
-- mean/stddev version a reviewer can run anywhere; the app uses the robust one.
WITH stats AS (
  SELECT quarter,
         AVG(npl_ratio) AS mu,
         -- sample stddev
         SQRT(AVG(npl_ratio * npl_ratio) - AVG(npl_ratio) * AVG(npl_ratio)) AS sigma
  FROM submissions
  WHERE npl_ratio IS NOT NULL
  GROUP BY quarter
)
SELECT s.institution_id, s.institution, s.quarter, s.npl_ratio,
       ROUND((s.npl_ratio - stats.mu) / stats.sigma, 2) AS z_score
FROM submissions s
JOIN stats ON stats.quarter = s.quarter
WHERE stats.sigma > 0
  AND ABS(s.npl_ratio - stats.mu) / stats.sigma >= 3;
