-- Substitute approved principals; run as the authorized Entra database admin.
-- Managed identity -> contained user is not created by ARM/Bicep.
CREATE USER [REPLACE_WITH_FACTORY_NAME] FROM EXTERNAL PROVIDER;
GRANT INSERT,DELETE,SELECT ON OBJECT::retail.stage_lines TO [REPLACE_WITH_FACTORY_NAME];
GRANT ADMINISTER DATABASE BULK OPERATIONS TO [REPLACE_WITH_FACTORY_NAME];
GRANT EXECUTE ON OBJECT::retail.publish_day TO [REPLACE_WITH_FACTORY_NAME];
-- Ownership chaining/EXECUTE and COPY permissions must be live tested.
-- Do not grant db_owner as an automatic workaround.
CREATE USER [REPLACE_WITH_ANALYST_GROUP] FROM EXTERNAL PROVIDER;
GRANT SELECT ON OBJECT::retail.daily_revenue TO [REPLACE_WITH_ANALYST_GROUP];
GRANT SELECT ON OBJECT::retail.country_revenue TO [REPLACE_WITH_ANALYST_GROUP];
GRANT SELECT ON OBJECT::retail.batch_quality TO [REPLACE_WITH_ANALYST_GROUP];
