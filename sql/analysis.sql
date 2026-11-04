-- Run against warehouse.duckdb. These are SELECTs on local, committed data.

-- 1. Finance reconciliation: positive lines + signed negative lines = net GBP.
SELECT SUM(positive_sales) AS positive_sales_gbp,
       SUM(negative_adjustments) AS negative_adjustments_gbp,
       SUM(net_revenue) AS net_revenue_gbp,
       SUM(positive_sales)+SUM(negative_adjustments)-SUM(net_revenue) AS unexplained_gbp
FROM daily_revenue;

-- 2. Month trends. December 2011 is partial; do not compare raw full-month totals.
SELECT date_trunc('month',business_date)::DATE AS month,
       COUNT(DISTINCT business_date) AS observed_business_dates,
       SUM(line_count) AS accepted_lines,SUM(positive_sales) AS positive_sales_gbp,
       SUM(negative_adjustments) AS negative_adjustments_gbp,SUM(net_revenue) AS net_revenue_gbp
FROM daily_revenue GROUP BY month ORDER BY month;

-- 3. Country mix. This is one historical retailer, not national market share.
SELECT c.country,SUM(d.line_count) AS accepted_lines,SUM(d.net_revenue) AS net_revenue_gbp,
       SUM(d.negative_adjustments) AS signed_adjustments_gbp
FROM daily_revenue d JOIN dim_country c USING(country_key)
GROUP BY c.country ORDER BY net_revenue_gbp DESC,c.country;

-- 4. Active daily version and retained lineage; accepted + quarantine conservation.
SELECT c.business_date,c.source_sha256,b.raw_rows,b.accepted_rows,b.quarantined_rows,
       b.raw_rows=b.accepted_rows+b.quarantined_rows AS conserves_rows,
       w.source_url,w.captured_at AS source_captured_utc
FROM current_batches c JOIN batch_versions b USING(business_date,source_sha256)
JOIN workbook_sources w USING(source_sha256) ORDER BY business_date;

-- 5. Product codes can have multiple descriptions. Inspect observed versions.
SELECT p.stock_code,COUNT(DISTINCT p.product_key) AS observed_description_versions,
       SUM(f.quantity) AS signed_units,SUM(f.line_amount) AS signed_revenue_gbp
FROM fact_sales f JOIN dim_product p USING(product_key)
GROUP BY p.stock_code ORDER BY signed_revenue_gbp DESC,p.stock_code LIMIT 20;

-- 6. Completeness and suspicious source patterns, never auto-deleted.
SELECT SUM(unknown_customer_lines) AS unknown_customer_lines,
       SUM(zero_value_lines) AS zero_value_lines,SUM(candidate_duplicate_lines) AS candidate_duplicate_lines,
       SUM(cancellation_lines) AS cancellation_lines,
       SUM(cancellation_sign_mismatch_lines) AS cancellation_sign_mismatch_lines,
       SUM(negative_price_lines) AS negative_price_lines
FROM daily_revenue;

-- 7. Quarantine reason occurrence. A row may carry more than one reason.
SELECT reason,SUM(row_count) AS reason_occurrences FROM quality_summary
GROUP BY reason ORDER BY reason_occurrences DESC,reason;

-- 8. Retained versions and run attempts. Multiple runs do not imply duplicated facts.
SELECT status,COUNT(*) AS attempts,COUNT(*) FILTER(WHERE replayed) AS replayed_attempts
FROM run_audit GROUP BY status ORDER BY status;
