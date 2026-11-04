CREATE VIEW retail.daily_revenue AS
 SELECT business_date,COUNT_BIG(*) AS invoice_lines,
   SUM(CASE WHEN line_amount>0 THEN line_amount ELSE 0 END) AS positive_sales_gbp,
   SUM(CASE WHEN line_amount<0 THEN line_amount ELSE 0 END) AS negative_adjustments_gbp,
   SUM(line_amount) AS net_sales_gbp,
   SUM(CASE WHEN line_amount=0 THEN 1 ELSE 0 END) AS zero_value_lines,
   SUM(CASE WHEN customer_key=0 THEN 1 ELSE 0 END) AS unknown_customer_lines
 FROM retail.fact_invoice_line GROUP BY business_date;
GO
CREATE VIEW retail.country_revenue AS
 SELECT f.business_date,c.country,COUNT_BIG(*) AS invoice_lines,SUM(f.line_amount) AS net_sales_gbp
 FROM retail.fact_invoice_line f JOIN retail.dim_country c ON c.country_key=f.country_key
 GROUP BY f.business_date,c.country;
GO
CREATE VIEW retail.batch_quality AS
 SELECT business_date,source_sha256,raw_rows,accepted_rows,quarantined_rows,net_sales,
   raw_rows-accepted_rows-quarantined_rows AS unexplained_rows,published_at_utc
 FROM retail.current_batches;
GO
-- Synapse Studio SQL examples (not a deployed dashboard):
SELECT * FROM retail.daily_revenue ORDER BY business_date;
SELECT country,SUM(net_sales_gbp) AS net_sales_gbp FROM retail.country_revenue
 GROUP BY country ORDER BY net_sales_gbp DESC;
SELECT * FROM retail.batch_quality ORDER BY business_date;
SELECT cancellation,negative_price,line_class,COUNT_BIG(*) AS lines,SUM(line_amount) AS signed_gbp
 FROM retail.fact_invoice_line GROUP BY cancellation,negative_price,line_class;
