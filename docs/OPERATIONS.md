# Operations and recovery

## Execution model

Serialize writers and report publishers per data directory. DuckDB provides process file locking; this implementation does not coordinate independent cloud workers or concurrent application threads. It sets two query threads and a 1 GB DuckDB memory target with local spill storage; that is not a total Python-process memory cap.

The source adapter permits a 40 MiB compressed download/workbook, at most 100 ZIP members, 250 MiB expanded archive content and 2 million worksheet data rows. It uses at most three download attempts, socket waits up to 45 seconds, and a 90-second budget checked between read/retry operations. A blocked socket can overrun that budget; it is not a strict wall-clock deadline. Workbook parsing is outside the download budget. The outer ZIP must contain exactly `Online Retail.xlsx`; no arbitrary archive paths are extracted.

The splitter archives bytes first and exposes a completed delivery set only after every date has been written and checksummed. Failed splitting can leave retained raw evidence but cannot replace the previous completed pointer. A repeat split can reuse an existing completed source. The loader verifies retained workbook identity and selected daily Parquet checksums/schema/counts before publishing each day.

The splitter caps its combined normalized-row buffers at 8,192 rows across all dates, writes closed temporary chunks and assembles one final daily file at a time. It does not keep one open writer per business date. At most 3,660 distinct business dates are accepted. These controls bound row buffers and file handles; workbook shared strings, unusually large cell values and library overhead still consume memory.

## Transaction boundary

Each business date is its own transaction: replace facts and quarantine for that date, insert newly observed dimension members, record source/version metadata, replace the current pointer, and commit. Failures after DELETE or just before COMMIT roll back the date. Successful earlier dates in a multi-date invocation remain committed if a later date fails. Audit attempts are outside the business transaction, so rollback evidence remains visible.

Report generation is separate from business commit. It reads a coherent transaction, writes a new generation and replaces `reports/latest.json` after its outputs are complete. A failed report can leave the database ahead of the latest published export; it does not roll back committed sales. Rerun `report` to recover. Do not make simultaneous export writers race on the same pointer.

## Recovery actions

| Symptom | What remains valid | Action |
|---|---|---|
| Header/date/schema rejection during split | Previously completed delivery pointer and warehouse | Inspect retained source, change the contract deliberately with tests, or correct the input; rerun split |
| Daily row rejection | Valid facts and explicit quarantine | Review reasons and original evidence; do not silently delete rejected records or invent values |
| Failure during a date transaction | Prior committed version of that date | Fix the failure and reload the same date/range; prior successful dates replay safely |
| New source omits an already published date inside selected range | Existing serving state | Investigate and design an explicit deletion workflow; an absent row/file is not a delete instruction |
| Older published SHA selected | Guard refuses silent regression | Review provenance, then use `--allow-revert` only for an intentional reactivation |
| Report generation fails | Already committed warehouse; prior report pointer | `retail-warehouse report --data-dir data/live` |
| Retained workbook or batch digest mismatch | Last verified serving state | Stop and restore the original file from verified backup; never edit the manifest to bless corruption |
| Process interrupted | Some dates may be committed; current date transaction recovers on reopen | Verify no writer remains, inspect audit/current batches, and rerun the selected interval |

To use a reviewed corrected workbook:

```bash
retail-warehouse split --file /path/to/reviewed-correction.xlsx --data-dir data/live
retail-warehouse load --data-dir data/live --start 2011-01-04 --end 2011-01-04
```

The file path above is illustrative. Do not claim the entire workbook was refreshed when only one date was selected. Reverting uses the same split/load sequence with the retained older workbook and the load flag `--allow-revert`.

## Monitoring and restore

Inspect `run_audit`, current batch counts, quarantine fraction, missing-customer coverage, cancellation/sign flags, negative prices, retained source versions and the report pointer. A successful batch with all rows quarantined is operationally complete but may be analytically unusable. Define business quality thresholds before automating consumption. Logs identify source/date/run context; a hard crash can leave an audit marked running. Errors before a date load, including fetch/split/manifest validation, appear in CLI stderr and do not create a daily database audit.

Stop writers before backing up `warehouse.duckdb`, any WAL, retained raw workbooks, complete batch sets and their pointers/manifests. For a rebuild, select the intended current source for each date from the registry and replay into a new directory; do not blindly load every historical source in arrival order. Verify per-date counts and decimal totals before switching consumers. Tests demonstrate local transactional and replay recovery. A complete backup/restore disaster-recovery drill is not claimed.

Raw and delivery versions have no automatic retention deletion. Review evidence/restore requirements before pruning them. Orphan report generations can be removed after stopping writers and preserving the generation referenced by `reports/latest.json`. Cleanup scripts do not remove unrelated directories.

## Azure boundary

The cloud deployment needs an approved account, region, service tiers/runtime, estimated AUD cost and cleanup plan before execution. See [AZURE.md](AZURE.md). Synapse dedicated SQL compute must be paused after a bounded lab; retained storage can still incur charges. No cloud scheduler or paid resource was activated by this repository's local validation.
