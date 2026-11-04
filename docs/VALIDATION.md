# Observed validation — 4 November 2026

**Everything reported here ran locally. Azure resources, Synapse SQL, permissions, cloud networking, performance and recovery have not been tested.** Data dates are historical 2010–2011; 2026 is the access/validation date.

## Tests actually run

Installed package on macOS ARM64, Python **3.14.7**, DuckDB **2.0.0**, PyArrow **26.0.0**, openpyxl **3.1.5**:

- **37 deterministic pipeline tests passed** in the observed final run (2.341 seconds), treating `ResourceWarning` as an error.
- **5 Azure preparation-adapter tests passed** locally (0.076 seconds). They do not use an Azure SDK, upload a blob or execute SQL.
- Python syntax compilation passed for source, scripts and cloud adapters.
- Two Bicep templates and development parameters compiled with Bicep **0.46.1**. Production parameters deliberately failed the dev-only contract. ADF JSON and both CI YAML definitions parsed successfully. Azure CLI's newer-version notice was not a template warning.

Tests cover reproducible synthetic workbook bytes; source-row identity; retained duplicate lines; exact signed penny arithmetic; quantity multiplication before penny rounding; Unknown customers; description versions; invalid values; bad headers/dates; all-quarantined batches; immutable source/batch checksums; corrected-date replacement; old-version guards; date-range backfills; per-date and multi-date rollback; report-pointer recovery; and bounded HTTP behavior.

The synthetic ten-row fixture yields **8 accepted / 2 quarantined**, GBP **25.00** positive amounts, **−5.13** negative adjustments and **19.87** net. These are invented test values. Failure injection occurs after a real transactional DELETE and before COMMIT; assertions compare the complete small business state. A later-date failure also verifies that the earlier successful date remains committed and can replay safely.

Review found and fixed zero/NULL reporting for an entirely quarantined dataset and formula strings accepted as identifiers. The splitter was changed to a global buffer and temporary chunk strategy; focused regressions use tiny buffers with interleaved dates, verify row identities and deterministic output, and check the date-limit failure preserves the previous pointer. The final full source run used that bounded implementation.

## Public-source smoke and independent reconciliation

The installed source adapter downloaded the [UCI ZIP](https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip), retained both ZIP and XLSX provenance, split the complete workbook and loaded all observed dates. The source was within the documented download/expanded-size/row limits. The ZIP-to-workbook identity link is retained locally. Exact file hashes and reuse terms are in [SOURCES.md](SOURCES.md).

| Observation | Result |
|---|---:|
| Source rows / accepted rows | **541,909 / 541,909** |
| Quarantined real-source rows | **0** |
| Observed business dates | **305** |
| Date range | **2010-12-01 to 2011-12-09** |
| Positive rounded line amounts | **GBP 10,666,684.54** |
| Signed negative adjustments | **GBP −918,936.61** |
| Net signed line total | **GBP 9,747,747.93** |
| Unknown-customer lines retained | **135,080** |
| Missing-description lines retained | **1,454** |
| Candidate duplicates retained beyond the first occurrence | **5,268** |
| Zero-value lines retained | **2,519** |
| C-prefixed invoice lines | **9,288** |
| Cancellation/quantity-sign flags | **1,336** |
| Negative-price lines retained | **2** |

Zero quarantine means these records satisfy this declared contract. It does not establish that every source value is accurate or every record represents a unique sale. The source website's missing-value metadata differs from the workbook's observed missingness; missing customers/descriptions are handled explicitly rather than dropping those transactions. Flags are not proof of fraud, errors or matched refunds.

An independent streaming XLSX reader, [source_oracle.py](../scripts/source_oracle.py), computed rows and monetary totals with Python Decimal **without importing the warehouse or reading generated Parquet**. Its counts and positive/negative/net totals matched the warehouse for **all 305 dates**, to the penny. December 2011 ends on the ninth; it must not be treated as a complete month.

Further observed checks:

1. All 541,909 physical source rows were present exactly once in facts, with Excel row numbers 2–541,910 and the expected source digest.
2. There were **zero dimension orphans**. Dimensions contained 4,373 customer members (including Unknown), 5,749 observed product/description versions, 38 country labels and 305 dates.
3. A full second load replayed **305 dates**, with zero newly loaded dates. Count/XOR/exact-sum row fingerprints were unchanged across nine business tables. Fingerprints are consistency checks, not cryptographic row-set equality proofs; deterministic small-fixture tests compare exact states.
4. A seven-calendar-date backfill (`2010-12-01` through `2010-12-07`) replayed **6 observed delivery dates**, with no business change. The source has no delivery for one date in that interval; no empty day was invented. The synthetic test independently covers seven actual daily deliveries.
5. Every field in **1,716 daily-country CSV rows**, **305 batch CSV rows**, and the empty quality CSV was compared with ordered SQL results, including headers.
6. All **8 analytical SQL statements** ran against the real warehouse.
7. Azure **prepare-only** conversion produced 305 flat Parquet deliveries containing the same 541,909 accepted rows and identical signed totals. No Azure credentials, SDK upload, ADF pipeline or Synapse runtime was exercised.

Evidence files: [local validation](../examples/live-validation-2026-11-04.json), [independent source oracle](../examples/source-oracle-2026-11-04.json), [report](../examples/report-2026-11-04.json), [SQL outputs](../examples/sql-results-2026-11-04.json), [cloud preparation](../examples/cloud-preparation-2026-11-04.json). Large source/row-level files and databases are excluded from Git.

## Reproduce the observed checks

```bash
python -m pip install .
python -W error::ResourceWarning -m unittest discover -s tests -v
python -W error::ResourceWarning -m unittest discover -s azure -p 'test_*.py' -v
python -m compileall -q src azure scripts
python azure/validate_infra.py

# After README's full live fetch and load, use the retained workbook:
python scripts/source_oracle.py \
  --workbook data/live/raw/43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d/source.xlsx \
  > data/independent-oracle.json
python scripts/validate_live.py --data-dir data/live --oracle data/independent-oracle.json
python scripts/run_queries.py --data-dir data/live

# Does not load Azure credentials or upload:
python azure/producer.py \
  --workbook data/live/raw/43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d/source.xlsx \
  --data-dir data/live --output-dir data/cloud-prepared --prepare-only
```

The retained filename uses the observed SHA. If UCI revises its workbook, inspect the new manifest and source; do not assert these exact counts or old path for changed bytes. `validate_live.py` is intentionally a full-source check, expecting one source version and complete coverage, rather than a general mixed-version warehouse monitor.

## Cloud evidence still missing

No Docker image build/run, image publication, Azure DevOps execution, Azure deployment/what-if, managed-identity or private-network test, ADF Copy or schedule activation, Synapse DDL/procedure execution, concurrent-publisher test, live alert delivery, cloud failure/restore drill or measured Azure cost has run. The suggested 30-minute daily-batch target remains a **future measurement target**, not a demonstrated cloud SLA. See [AZURE.md](AZURE.md) for deployment sequencing, deliberate guards and known gaps.
