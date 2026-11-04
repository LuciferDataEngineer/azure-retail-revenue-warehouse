# Azure target and validation boundary

**No Azure resource, subscription, billing account, container image, SQL pool or scheduled workload was created.** The local warehouse is DuckDB. Azure files are an implementation target with specific offline evidence; Synapse SQL, managed identities, network access, cloud transactions and performance remain untested.

The architecture is the requested **Container Apps Job → ADLS Gen2 daily Parquet → Data Factory → Synapse dedicated SQL pool → Synapse Studio SQL views**, with Azure Monitor failure signals. This is a historical delivery simulation over UCI 2010–2011 invoices, not a live retail integration.

## Implemented assets

| Files | Behavior | Evidence |
|---|---|---|
| `infra/main.bicep` | HNS storage/private containers; ADF and Synapse identities; scoped Blob roles; Entra-only Synapse workspace; separately opted-in DW100c pool and manual Container Apps job; ADF diagnostics and failure alert | Bicep 0.46.1 compilation only |
| `infra/orchestration.bicep`, `azure/adf/publish-date.json` | Ready-manifest lookup, identity guard, complete date staging and stored-procedure publication; one pipeline run at a time; daily lab trigger definition | Bicep and JSON parsed; runtime pending |
| `azure/prepare_batches.py` | Converts shared normalized Parquet to a flat Synapse contract, preserves accepted and quarantine rows, validates SHA/counts/physical row uniqueness and SQL width limits | Five offline tests passed; all 305 real date batches prepared locally |
| `azure/producer.py`, `Dockerfile` | Shared download/split adapter, managed-identity Blob upload, immutable content paths and ready markers published last | Prepare-only path executed; SDK upload and Docker build/runtime not executed |
| `azure/sql/01_schema.sql` | Heap stage/quarantine, replicated dimensions/registries, hash-distributed columnstore facts, statistics | Reviewed against dedicated-pool constraints; not parsed/executed by Synapse |
| `azure/sql/02_publish_day.sql` | Guarded row counts, signed money, dimension consistency, explicit revision gate and transactional date replacement | Source review only; cloud failure/replay tests pending |
| `azure/sql/03_views.sql`, `04_permissions.sql` | Revenue/quality views, useful SQL and explicit contained-user grants | Not executed |
| `azure-pipelines.yml` | Credential-free validation; opt-in foundation deployment with independent environment approval boundary | YAML parsed; Azure DevOps not run |

Observed locally on 4 November 2026: **two Bicep templates and development parameters compiled**, production parameters deliberately produced BCP033 because only `environment='dev'` is allowed, and Python cloud adapters passed syntax checks. The five adapter tests verify preservation of all rows and signed totals, deterministic output, byte corruption, count mismatches, unknown contracts and refusal to truncate long values.

The full local preparation test produced **305 daily files, 541,909 rows, zero quarantines**, and reconciled **GBP 10,666,684.54 positive line amounts − GBP 918,936.61 negative adjustments = GBP 9,747,747.93 net**. This evidence is in [cloud-preparation-2026-11-04.json](../examples/cloud-preparation-2026-11-04.json). No Azure SDK upload or SQL connection was involved.

## Free checks and preparation

From the repository root after installing the local package:

```bash
python -W error::ResourceWarning -m unittest discover -s azure -p 'test_*.py' -v
python -m compileall -q azure
# Requires Azure CLI/Bicep, but does not authenticate or deploy:
python azure/validate_infra.py

# Generate invented source data first; no external data is required for this example.
python scripts/generate_fixture.py --output data/fixtures/synthetic-retail.xlsx
python azure/producer.py --workbook data/fixtures/synthetic-retail.xlsx \
  --data-dir data/cloud-demo --output-dir data/cloud-prepared-demo --prepare-only
```

`--prepare-only` never imports an Azure credential. Omitting `--workbook` invokes the bounded public UCI source adapter. The optional SDK dependencies are pinned in `azure/requirements.txt`; they are needed only for the upload path/image. Docker uses Python 3.12, an unprivileged UID, and a restricted build context. The base image tag is not digest-pinned; a future deployment must resolve/scan and approve its actual digest, build the image and test it before publishing or running it.

## Contracts, publication and reader isolation

The source adapter and row normalization are shared with the local implementation. The cloud shape contract is `retail-synapse-v1`: all daily rows remain in one flat Parquet file; `is_valid` and JSON `reasons_json` replace the nested reasons array for dedicated SQL loading. Long modeled strings or payloads fail preparation, never truncate. Exact worksheet row ordinals and workbook SHA identify lines; repeated invoice/product pairs are not deduplicated.

The producer uploads the workbook once at `raw/<source-sha>/source.xlsx`, capture manifests at `raw/<source-sha>/captures/<uuid>.json`, and prepared files at `batches/prepared/retail-synapse-v1/<source-sha>/<date>.parquet`. Capture UUIDs intentionally preserve separate run metadata. Business-ready files and ready JSON are deterministic by contract/source/date. Repeated uploads use `overwrite=False`; an existing object is downloaded and its SHA compared before it is accepted as identical. These are application-level immutability checks, not WORM storage. A privileged storage writer can still change data.

Ready markers at `batches/ready/retail-synapse-v1/<source-sha>/<date>.json` are uploaded only after **all** workbook batch files upload. A failure midway through ready-marker publication can expose a subset of ready dates; each date is independently loadable, and retry completes remaining identical markers. This is not a whole-workbook distributed transaction. The producer records batch SHA and upload-content integrity checks; ADF/Synapse do not independently calculate a cryptographic hash of the staged file. Their guards instead reconcile the trusted ready manifest's identity, counts, row grain and signed totals. Storage identity/denial/tamper tests remain necessary.

ADF looks up an explicit source SHA/date, verifies the cloud contract and identity, then clears the **staging table only**, copies the entire prepared file with `MAXERRORS=0` and row skipping disabled, and calls `retail.publish_day`. A failed copy cannot reach the publication activity; retry clears partial staging before recopying. The SQL procedure rejects incompatible manifests, duplicate row identity, missing required fields, inconsistent line classifications/rounded products, aggregate mismatches and conflicting dimension attributes.

Within one transaction it inserts new immutable dimension versions, replaces that date's facts/quarantine, updates the current pointer and retains first-published version metadata. It checks published counts, dimension uniqueness and fact-to-dimension references before commit. An already-current source/day/batch returns without changing business tables. Any changed active date, including a revert, requires `allowRevision=true`. This cloud approval gate is deliberately stricter than the local initial-revision behavior.

**READ_COMMITTED_SNAPSHOT is mandatory.** Dedicated SQL pool otherwise defaults to READ UNCOMMITTED, which could expose partial uncommitted changes. Enable the database option from `master` before use; the procedure refuses to publish if the flag is absent/off. A future test must prove that concurrent readers see the previous complete date until commit. There is no claim that a local DuckDB transaction establishes Synapse behavior.

There are no declared `PRIMARY KEY ... NOT ENFORCED` or `UNIQUE ... NOT ENFORCED` constraints. Dedicated pool would not enforce them and its optimizer could assume incorrect uniqueness. The implementation uses explicit checks under a **single-publisher** contract. ADF `concurrency=1` serializes this pipeline only: do not run a second factory, pipeline or manual SQL writer against the same stage or tables. A distributed lock/lease across independent orchestrators is not implemented.

## Future approved deployment sequence

These are future actions. No account or spending approval currently exists.

1. Prepare an AUD cost/region/runtime plan and obtain explicit approval. Choose a dedicated resource group containing only this lab, an approved Entra administrator group, and a workload-identity service connection. Configure independent approval/checks on the Azure DevOps `retail-lab-approved` environment. Do not grant subscription Owner to bypass setup problems.
2. Validate templates and inspect a resource-group what-if. Defaults create nothing. The optional DevOps deployment creates the foundation only, with `deployDedicatedPool=false` and `deployProducer=false`. Account/group placeholders must be replaced with reviewed values. No application secret is required and no Key Vault is provisioned; introducing SQL-password authentication would require a separate reviewed secret design.
3. Verify Entra-only workspace creation, the administrator assignment, storage role propagation, workspace filesystem access and identity boundaries. These provider-level behaviors are untested by compilation. Confirm the chosen non-UTF-8 `Latin1_General_100_BIN2` collation is available in the actual pool; character attributes use NVARCHAR. This is a dedicated-pool target, never a serverless-SQL substitute.
4. Create the explicitly approved DW100c pool for a bounded test window. The foundation template supports this with a separate opt-in. Configure reviewed SQL firewall/private access. The template does not add a broad “allow all Azure services” firewall rule. Public endpoint settings in this lab do not imply that SQL is reachable; permitted connectivity must be configured and tested deliberately.
5. Connect as the authorized Entra administrator. Enable READ_COMMITTED_SNAPSHOT from `master`, then run `azure/sql/01_schema.sql`, `02_publish_day.sql`, `03_views.sql` and substituted `04_permissions.sql` against a **fresh dedicated database**. The bootstrap scripts deliberately do not erase/recreate existing business tables; rerunning setup is not a recovery mechanism. Check the ADF contained user, COPY permissions, procedure ownership chaining and analyst view-only access. Never grant `db_owner` automatically as a workaround.
6. Build/scan the producer image and publish it to an approved registry. The provided job expects a reviewed public image reference; private-registry managed-identity pull configuration is a documented remaining step if required. Opt into the manual Container Apps Job, validate its 1 CPU/2 GiB and 30-minute timeout against the actual workload, and verify Blob permissions. The template does not start it. Execute one approved run and inspect ready manifests; no hidden Container Apps schedule exists.
7. Deploy the second-phase orchestration module with the actual factory/account/workspace/pool names. A newly created schedule trigger is stopped by the service; the code does not issue a trigger-start operation. Stop and inspect any existing trigger before redeploying. Its default future start time is intentionally inert and must be reviewed. The supplied daily lab trigger repeats a selected historical date to demonstrate replay; it does not advance a synthetic calendar. For a seven-date backfill, invoke the same pipeline serially with seven dates from the ready manifest. Automated historical-date advancement is future work.
8. Manually execute one synthetic date first, verify the expected rows/money, then run bounded real dates and the acceptance cases below. Only start a reviewed schedule during its approved test window. Save queries/views in Synapse Studio; no hosted dashboard or published BI report currently exists.
9. Collect actual runtime, cost, security and recovery evidence. Stop triggers, pause the dedicated pool and stop producer executions when the approved window ends. Update the project's status only with tests that actually ran.

## Cloud acceptance work still required

- Compare all 305 date counts and penny-level sums against the independently recorded local source oracle. A 30-minute daily-batch target is a target, not a measured result.
- Replay a day unchanged; inject a corrected source, exercise explicit revision/revert, and show other dates remain unchanged. Preserve all physical duplicate lines and unknown-customer rows.
- Fail copy midway, fail SQL after DELETE and before COMMIT, lose the success response after commit, and repeat. Prove prior complete data remains visible using concurrent readers under RCSI.
- Exercise invalid schema, corrupt batch bytes, wrong manifest counts, partial ready publication, an unknown customer, signed/zero amounts, oversize text and dimension-key conflicts.
- Run two attempted publishers to prove the operational serialization boundary; do not infer protection from unenforced keys. Deliberate out-of-band writes are outside the current contract.
- Verify managed-identity access to only intended containers, denial of analyst base-table/raw access, Entra administration, SQL firewall/private routes, COPY permissions and credential-free execution.
- Trigger an ADF failure and confirm delivery to an approved action group. The default alert has **no notification receiver**. ADF run logs are configured; Container Apps console diagnostic routing, data freshness/reject alerts and comprehensive lineage dashboards remain future work.
- Exercise database/raw restore into a separate environment and compare counts/decimal totals. No cloud backup/restore or regional disaster-recovery evidence is claimed.

## Cost and cleanup

A future estimate should specify region (Australia East is the provisional template default), DW100c availability, hours from resume through pause, number/duration of Container Apps executions, ADF activities/data movement, storage/transactions, monitoring volume/retention and registry choice. Include currency conversion/taxes and contingency before approval. Neither this worksheet nor the template is a price estimate. Free-account/trial credits are not assurance that this stack is free.

Pause the dedicated pool immediately after testing: compute charges stop while storage can continue. Stop all manually started triggers and job executions, retain the approved raw/manifest/evidence backup, review the lab resource group and any workspace-managed resources, then delete only confirmed project resources when retention allows. Verify remaining storage/log/registry charges. Budget alerts are notifications, not a universal hard spending limit. No cleanup command in this repository deletes resources automatically.

Production parameters are deliberately blocked. Private endpoints/DNS, managed integration networking, controlled egress, identity lifecycle, image supply-chain controls, explicit retention, cost automation and disaster recovery must be designed and tested before relaxing that guard.

## Primary references

Reviewed 4 November 2026; recheck before any deployment.

- [Dedicated SQL transactions](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/sql-data-warehouse-develop-transactions): isolation, transaction limits and rollback-first error handling.
- [Dedicated-pool table constraints](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/sql-data-warehouse-table-constraints): unenforced keys and query correctness.
- [ADF Synapse connector](https://learn.microsoft.com/en-us/azure/data-factory/connector-azure-sql-data-warehouse): managed identity, COPY staging and required database permissions.
- [Synapse collation support](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/reference-collation-types), [Entra authentication](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/authentication-aad-overview), [workspace ARM schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.synapse/2021-06-01/workspaces), and [Container Apps Job ARM schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2024-03-01/jobs).
- [Creating an ADF trigger](https://learn.microsoft.com/en-us/powershell/module/az.datafactory/set-azdatafactoryv2trigger) and [trigger lifecycle API](https://learn.microsoft.com/en-us/rest/api/datafactory/triggers?view=rest-datafactory-2018-06-01).
- [Pause/resume dedicated compute](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/pause-and-resume-compute-portal), [Synapse pricing](https://azure.microsoft.com/en-us/pricing/details/synapse-analytics/), [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/) and [ADF pricing](https://azure.microsoft.com/en-us/pricing/details/data-factory/data-pipeline/) are inputs for the future approved cost plan.
