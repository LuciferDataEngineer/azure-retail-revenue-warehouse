-- Exactly one publisher across all pipelines and manual callers is required.
-- ADF concurrency=1 alone does not serialize independent factories or SQL callers.
CREATE PROCEDURE retail.publish_day
 @business_date date, @source_sha256 varchar(64), @batch_sha256 varchar(64),
 @expected_rows bigint, @expected_accepted bigint, @expected_net decimal(38,2),
 @allow_revision bit=0
AS
BEGIN
 SET NOCOUNT ON;
 IF ISNULL((SELECT is_read_committed_snapshot_on FROM sys.databases WHERE name=DB_NAME()),0)<>1
   THROW 50001,'Enable READ_COMMITTED_SNAPSHOT before publication',1;
 IF @expected_rows IS NULL OR @expected_accepted IS NULL OR @expected_net IS NULL OR @business_date IS NULL OR @allow_revision IS NULL
   OR @expected_rows<1 OR @expected_accepted<0 OR @expected_accepted>@expected_rows
   THROW 50002,'Invalid ready manifest counts',1;
 IF @source_sha256 IS NULL OR @batch_sha256 IS NULL OR LEN(@source_sha256)<>64 OR LEN(@batch_sha256)<>64
   OR @source_sha256 LIKE '%[^0-9a-f]%' OR @batch_sha256 LIKE '%[^0-9a-f]%'
   THROW 50003,'Invalid manifest source or batch digest',1;
 IF (SELECT COUNT_BIG(*) FROM retail.stage_lines)<>@expected_rows
   THROW 50004,'Staged row count differs from ready manifest',1;
 IF EXISTS (SELECT 1 FROM retail.stage_lines WHERE business_date<>@business_date OR source_sha256<>@source_sha256 OR source_row<2)
   THROW 50005,'Stage contains a different date/source or invalid physical row',1;
 IF EXISTS (SELECT source_row FROM retail.stage_lines GROUP BY source_row HAVING COUNT_BIG(*)<>1)
   THROW 50006,'Duplicate source-row identity in staging',1;
 IF (SELECT COUNT_BIG(*) FROM retail.stage_lines WHERE is_valid=1)<>@expected_accepted
   THROW 50007,'Accepted row count differs from ready manifest',1;
 IF EXISTS (SELECT 1 FROM retail.stage_lines WHERE (is_valid=1 AND reasons_json<>N'[]') OR (is_valid=0 AND reasons_json=N'[]'))
   THROW 50008,'Accepted/quarantine decision conflicts with reason payload',1;
 IF EXISTS (SELECT 1 FROM retail.stage_lines WHERE is_valid=1 AND
   (invoice_no IS NULL OR stock_code IS NULL OR country IS NULL OR quantity IS NULL OR unit_price IS NULL
    OR line_amount IS NULL OR invoice_at IS NULL OR CAST(invoice_at AS date)<>business_date
    OR product_key IS NULL OR country_key IS NULL OR customer_key IS NULL
    OR cancellation IS NULL OR cancellation_sign_mismatch IS NULL OR negative_price IS NULL
    OR line_class IS NULL OR line_class NOT IN ('positive_sales','negative_adjustment','zero_value')))
   THROW 50009,'Accepted row lacks required serving values',1;
 IF EXISTS (SELECT 1 FROM retail.stage_lines WHERE is_valid=1 AND
   (line_amount<>CAST(ROUND(CAST(quantity AS decimal(19,0))*unit_price,2) AS decimal(18,2))
    OR (line_amount>0 AND line_class<>'positive_sales')
    OR (line_amount<0 AND line_class<>'negative_adjustment')
    OR (line_amount=0 AND line_class<>'zero_value')))
   THROW 50010,'Signed line amount or class fails reconciliation',1;
 IF COALESCE((SELECT SUM(line_amount) FROM retail.stage_lines WHERE is_valid=1),0)<>@expected_net
   THROW 50011,'Signed net differs from ready manifest',1;
 IF EXISTS (SELECT business_date FROM retail.current_batches GROUP BY business_date HAVING COUNT_BIG(*)>1)
   THROW 50012,'Current batch registry is not unique',1;
 IF EXISTS (SELECT business_date,source_sha256 FROM retail.batch_versions GROUP BY business_date,source_sha256 HAVING COUNT_BIG(*)>1)
   THROW 50013,'Historical batch registry is not unique',1;
 IF EXISTS (SELECT 1 FROM retail.batch_versions WHERE business_date=@business_date AND source_sha256=@source_sha256 AND batch_sha256<>@batch_sha256)
   THROW 50014,'Same source/day changed under the same cloud contract',1;
 IF EXISTS (SELECT 1 FROM retail.current_batches WHERE business_date=@business_date AND source_sha256=@source_sha256 AND batch_sha256=@batch_sha256)
   RETURN; -- attempt occurred, business state did not change.
 IF @allow_revision=0 AND EXISTS (SELECT 1 FROM retail.current_batches WHERE business_date=@business_date)
   THROW 50015,'Changed date requires explicit revision approval',1;
 -- Validate dimension keys before using them; SQL pool does not enforce unique keys.
 IF EXISTS (SELECT product_key FROM retail.dim_product GROUP BY product_key HAVING COUNT_BIG(*)>1)
   OR EXISTS (SELECT customer_key FROM retail.dim_customer GROUP BY customer_key HAVING COUNT_BIG(*)>1)
   OR EXISTS (SELECT country_key FROM retail.dim_country GROUP BY country_key HAVING COUNT_BIG(*)>1)
   OR EXISTS (SELECT business_date FROM retail.dim_date GROUP BY business_date HAVING COUNT_BIG(*)>1)
   THROW 50016,'Dimension key uniqueness failed',1;
 IF (SELECT COUNT_BIG(*) FROM retail.dim_customer WHERE customer_key=0 AND customer_id IS NULL AND is_unknown=1)<>1
   THROW 50021,'Unknown customer member is absent or invalid',1;
 IF EXISTS (SELECT 1 FROM retail.stage_lines s JOIN retail.dim_product d ON d.product_key=s.product_key
     WHERE s.is_valid=1 AND (d.stock_code<>s.stock_code OR d.description<>s.description
       OR (d.description IS NULL AND s.description IS NOT NULL) OR (d.description IS NOT NULL AND s.description IS NULL)))
   OR EXISTS (SELECT 1 FROM retail.stage_lines s JOIN retail.dim_country d ON d.country_key=s.country_key
     WHERE s.is_valid=1 AND d.country<>s.country)
   OR EXISTS (SELECT 1 FROM retail.stage_lines s JOIN retail.dim_customer d ON d.customer_key=s.customer_key
     WHERE s.is_valid=1 AND (d.customer_id<>s.customer_id OR
       (d.customer_id IS NULL AND s.customer_id IS NOT NULL) OR (d.customer_id IS NOT NULL AND s.customer_id IS NULL)))
   THROW 50019,'Existing dimension key has conflicting attributes',1;
 BEGIN TRY
   BEGIN TRANSACTION;
   INSERT INTO retail.dim_product
     SELECT DISTINCT s.product_key,s.stock_code,s.description FROM retail.stage_lines s
     WHERE s.is_valid=1 AND NOT EXISTS (SELECT 1 FROM retail.dim_product d WHERE d.product_key=s.product_key);
   INSERT INTO retail.dim_customer
     SELECT DISTINCT s.customer_key,s.customer_id,CAST(0 AS bit) FROM retail.stage_lines s
     WHERE s.is_valid=1 AND s.customer_key<>0 AND NOT EXISTS (SELECT 1 FROM retail.dim_customer d WHERE d.customer_key=s.customer_key);
   INSERT INTO retail.dim_country
     SELECT DISTINCT s.country_key,s.country FROM retail.stage_lines s
     WHERE s.is_valid=1 AND NOT EXISTS (SELECT 1 FROM retail.dim_country d WHERE d.country_key=s.country_key);
   IF NOT EXISTS (SELECT 1 FROM retail.dim_date WHERE business_date=@business_date)
     INSERT INTO retail.dim_date VALUES (@business_date,YEAR(@business_date),MONTH(@business_date),DAY(@business_date));
   -- Test deployment must inject failure after DELETE and before COMMIT.
   DELETE FROM retail.fact_invoice_line WHERE business_date=@business_date;
   DELETE FROM retail.quarantine WHERE business_date=@business_date;
   INSERT INTO retail.fact_invoice_line
     SELECT business_date,source_sha256,source_row,invoice_no,invoice_at,product_key,customer_key,country_key,
       quantity,unit_price,line_amount,line_class,cancellation,cancellation_sign_mismatch,negative_price
     FROM retail.stage_lines WHERE is_valid=1;
   INSERT INTO retail.quarantine
     SELECT business_date,source_sha256,source_row,reasons_json,raw_payload FROM retail.stage_lines WHERE is_valid=0;
   DELETE FROM retail.current_batches WHERE business_date=@business_date;
   INSERT INTO retail.current_batches VALUES (@business_date,@source_sha256,@batch_sha256,@expected_rows,
       @expected_accepted,@expected_rows-@expected_accepted,@expected_net,SYSUTCDATETIME());
   IF NOT EXISTS (SELECT 1 FROM retail.batch_versions WHERE business_date=@business_date AND source_sha256=@source_sha256)
     INSERT INTO retail.batch_versions VALUES (@business_date,@source_sha256,@batch_sha256,@expected_rows,
       @expected_accepted,@expected_rows-@expected_accepted,@expected_net,SYSUTCDATETIME());
   -- Checks after INSERT must precede COMMIT; do not trust unenforced constraints.
   IF (SELECT COUNT_BIG(*) FROM retail.fact_invoice_line WHERE business_date=@business_date)<>@expected_accepted
      OR (SELECT COUNT_BIG(*) FROM retail.quarantine WHERE business_date=@business_date)<>@expected_rows-@expected_accepted
     THROW 50017,'Publication count mismatch',1;
   IF EXISTS (SELECT product_key FROM retail.dim_product GROUP BY product_key HAVING COUNT_BIG(*)>1)
      OR EXISTS (SELECT customer_key FROM retail.dim_customer GROUP BY customer_key HAVING COUNT_BIG(*)>1)
      OR EXISTS (SELECT country_key FROM retail.dim_country GROUP BY country_key HAVING COUNT_BIG(*)>1)
     THROW 50018,'New dimension keys are not unique',1;
   IF EXISTS (SELECT 1 FROM retail.fact_invoice_line f
     LEFT JOIN retail.dim_product p ON p.product_key=f.product_key
     LEFT JOIN retail.dim_customer c ON c.customer_key=f.customer_key
     LEFT JOIN retail.dim_country n ON n.country_key=f.country_key
     LEFT JOIN retail.dim_date d ON d.business_date=f.business_date
     WHERE f.business_date=@business_date AND
       (p.product_key IS NULL OR c.customer_key IS NULL OR n.country_key IS NULL OR d.business_date IS NULL))
     THROW 50020,'Published fact has a missing dimension reference',1;
   COMMIT TRANSACTION;
 END TRY
 BEGIN CATCH
   -- Dedicated pool error state can be -2. Roll back before selecting error info.
   IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
   THROW;
 END CATCH;
END;
GO
