-- Azure Synapse DEDICATED SQL pool only. Not executed against Azure.
-- Before loading, connect to master and enable:
-- ALTER DATABASE retail SET READ_COMMITTED_SNAPSHOT ON;
-- The publication procedure refuses READ UNCOMMITTED/default isolation.
CREATE SCHEMA retail;
GO
CREATE TABLE retail.stage_lines (
 business_date date NOT NULL, source_sha256 varchar(64) NOT NULL, source_row bigint NOT NULL,
 invoice_no nvarchar(64) NULL, stock_code nvarchar(64) NULL, description nvarchar(1024) NULL,
 quantity bigint NULL, invoice_at datetime2(6) NULL, unit_price decimal(18,4) NULL,
 customer_id bigint NULL, country nvarchar(128) NULL, line_amount decimal(18,2) NULL,
 line_class varchar(24) NULL, cancellation bit NULL, cancellation_sign_mismatch bit NULL,
 negative_price bit NULL, product_key varchar(64) NULL, customer_key bigint NULL,
 country_key varchar(64) NULL, is_valid bit NOT NULL, reasons_json nvarchar(4000) NOT NULL,
 raw_payload nvarchar(4000) NOT NULL
) WITH (DISTRIBUTION=ROUND_ROBIN, HEAP);
GO
CREATE TABLE retail.dim_product (
 product_key varchar(64) NOT NULL,stock_code nvarchar(64) NOT NULL,description nvarchar(1024) NULL
) WITH (DISTRIBUTION=REPLICATE, HEAP);
CREATE TABLE retail.dim_customer (
 customer_key bigint NOT NULL,customer_id bigint NULL,is_unknown bit NOT NULL
) WITH (DISTRIBUTION=REPLICATE, HEAP);
INSERT INTO retail.dim_customer VALUES (0,NULL,1);
CREATE TABLE retail.dim_country (
 country_key varchar(64) NOT NULL,country nvarchar(128) NOT NULL
) WITH (DISTRIBUTION=REPLICATE, HEAP);
CREATE TABLE retail.dim_date (
 business_date date NOT NULL,year_number int NOT NULL,month_number int NOT NULL,day_number int NOT NULL
) WITH (DISTRIBUTION=REPLICATE, HEAP);
GO
CREATE TABLE retail.fact_invoice_line (
 business_date date NOT NULL,source_sha256 varchar(64) NOT NULL,source_row bigint NOT NULL,
 invoice_no nvarchar(64) NOT NULL,invoice_at datetime2(6) NOT NULL,
 product_key varchar(64) NOT NULL,customer_key bigint NOT NULL,country_key varchar(64) NOT NULL,
 quantity bigint NOT NULL,unit_price decimal(18,4) NOT NULL,line_amount decimal(18,2) NOT NULL,
 line_class varchar(24) NOT NULL,cancellation bit NOT NULL,cancellation_sign_mismatch bit NOT NULL,
 negative_price bit NOT NULL
) WITH (DISTRIBUTION=HASH(product_key),CLUSTERED COLUMNSTORE INDEX);
CREATE TABLE retail.quarantine (
 business_date date NOT NULL,source_sha256 varchar(64) NOT NULL,source_row bigint NOT NULL,
 reasons_json nvarchar(4000) NOT NULL,raw_payload nvarchar(4000) NOT NULL
) WITH (DISTRIBUTION=ROUND_ROBIN,HEAP);
CREATE TABLE retail.current_batches (
 business_date date NOT NULL,source_sha256 varchar(64) NOT NULL,batch_sha256 varchar(64) NOT NULL,
 raw_rows bigint NOT NULL,accepted_rows bigint NOT NULL,quarantined_rows bigint NOT NULL,
 net_sales decimal(38,2) NOT NULL,published_at_utc datetime2(6) NOT NULL
) WITH (DISTRIBUTION=REPLICATE,HEAP);
CREATE TABLE retail.batch_versions (
 business_date date NOT NULL,source_sha256 varchar(64) NOT NULL,batch_sha256 varchar(64) NOT NULL,
 raw_rows bigint NOT NULL,accepted_rows bigint NOT NULL,quarantined_rows bigint NOT NULL,
 net_sales decimal(38,2) NOT NULL,first_published_at_utc datetime2(6) NOT NULL
) WITH (DISTRIBUTION=REPLICATE,HEAP);
GO
-- No PRIMARY KEY/UNIQUE NOT ENFORCED declarations: they can let the optimizer
-- assume uniqueness that Synapse does not enforce. Publication checks it itself.
CREATE STATISTICS fact_date_stats ON retail.fact_invoice_line(business_date);
CREATE STATISTICS fact_product_stats ON retail.fact_invoice_line(product_key);
GO
