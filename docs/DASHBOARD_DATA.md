# Dashboard data and reproducibility

The GitHub Pages dashboard is a **reviewed snapshot as of 4 November 2026**, using aggregate evidence from the two published Azure-series implementations. It is not a live business feed or a deployed Azure monitor. Three further projects are explicitly queued. The dashboard never fetches credentials, databases, raw customer records or individual taxi records in a visitor's browser.

## Build the snapshot

The standard-library builder [scripts/build_dashboard_data.py](../scripts/build_dashboard_data.py) reads six public aggregate JSON files at immutable Git commits and verifies their SHA-256 digests before processing them. It produces [site/data/dashboard.json](../site/data/dashboard.json) deterministically.

```bash
# Default: download the six small, pinned public evidence files and rebuild.
python3 scripts/build_dashboard_data.py

# Rebuild in memory and compare every output byte with the existing bundle.
python3 scripts/build_dashboard_data.py --check

# Offline: check the bundle's row conservation, signed money and chart scopes.
python3 scripts/build_dashboard_data.py --validate-only

# Optional local source mode, if the dated sibling project folders exist.
# Their contents must match the same pinned digests as the public files.
python3 scripts/build_dashboard_data.py --local-root .. --check
```

Downloads allow no credentials, use HTTPS with a 15-second socket timeout, permit at most 1 MiB per file, and check a 90-second overall budget between requests. This budget is not a strict wall-clock interruption of a response read. A changed checksum fails closed, leaving the existing output untouched. There are no automatic schema upgrades or unreviewed `main`-branch refreshes. Output uses a temporary file and atomic rename after successful parsing and checks.

To refresh to a newly validated source version, review the new source evidence, update the commit/hash manifest and dated project metadata in the builder, rerun the reconciliation and rebuild the dashboard app. A later source snapshot does not establish new Azure runtime evidence. Updating this snapshot does not start or purchase a cloud workload.

## Evidence pinned for this snapshot

| Project | Evidence commit | Local tests | Source scope |
|---|---|---:|---|
| [Retail](https://github.com/LuciferDataEngineer/azure-retail-revenue-warehouse/tree/06c9566611b3ff7c1dfd41c4b5abf21033db4499) | `06c9566611b3ff7c1dfd41c4b5abf21033db4499` | 42 | One historical UK retailer, 1 December 2010–9 December 2011 |
| [Mobility](https://github.com/LuciferDataEngineer/azure-urban-mobility-lakehouse/tree/ce32b70f83d6e8593cc2e768ae5ff95b28888a7b) | `ce32b70f83d6e8593cc2e768ae5ff95b28888a7b` | 43 | NYC yellow-taxi source months January–March 2024 |

The six pinned inputs are each project's `report`, `sql-results` and `live-validation` JSON files. Their exact URLs, commits, byte counts and digests travel with the output under `provenance.inputs`. Project validation, README, source attribution and CI evidence links are also included. Test counts and roadmap status are a dated editorial snapshot from the existing validation documents and portfolio backlog, not a live GitHub query.

## Meaning and interaction boundaries

- **Retail amounts are GBP; mobility amounts are USD.** Do not sum or directly compare these currencies. Monetary fields are strings in JSON to preserve exact pennies/cents; the builder reconciles with Python `Decimal`.
- **Retail monthly counts, positive amounts, negative amounts and net** include every accepted signed line. The last month, December 2011, is partial through the ninth. It is not a complete-month decline or a current retail indicator.
- **Retail countries and top 20 stock codes** cover the entire historical source period. The committed evidence has no month-by-country/product cross-table, so a month selector must not pretend to filter those breakdowns. A stock-code ranking includes administrative/non-product codes such as DOT and POST.
- **Retail warning counts overlap.** Missing customers, candidate duplicates, zero values and sign mismatches are retained flags; they are not quarantined rows. Zero real-source quarantine establishes compliance with this declared contract, not perfect source truth.
- **Mobility monthly totals include all accepted records**, with ordinary and negative-adjustment groups kept separate. Net recorded charges exclude cash tips and are not profit or driver take-home pay.
- **Mobility hour-of-day and top 10 zones use ordinary records only:** 9,415,026 accepted records with neither original fare nor original total negative. This excludes 136,895 signed-adjustment records. Their denominator differs from the 9,551,921 accepted-record total. These views cover the complete three-month period, independently of any month selector.
- Hours are recorded NYC civil hours, not UTC or precise elapsed intervals. Mean duration is a wall-clock statistic and can be affected by daylight-saving transitions. Zone names use a November 2026 lookup snapshot; historical names were not independently verified.
- **Mobility reason counts may overlap.** The quarantine total counts records. Reason counts count occurrences; do not generally sum reasons to derive unique rejected records.
- A portfolio total of 10,096,687 source rows describes the number of records processed across two different source populations. It is not a combined sales/trip business metric. The 85 local tests likewise describe two test suites, not Azure runtime checks.
- Azure deployment, security, performance and recovery remain unvalidated for both projects. A published local implementation and passing GitHub CI do not establish those cloud properties.

## Bundle contract

`schema_version` is `portfolio-dashboard-v1`. Top-level fields are `snapshot_date`, `owner`, `is_live_feed`, `portfolio`, `retail`, `mobility` and `provenance`.

Each analytical project contains `period`, `totals`, `monthly`, `quality`, `view_scope`, `definitions`, `validation` and `sources`. Retail adds `countries` and `top_products`; mobility adds `hourly` and `top_zones`. Published roadmap entries contain repository/evidence/CI links; queued entries have `repo_url: null` and no invented test counts. The frontend should use the supplied view scopes, definitions and historical labels.

## Observed builder verification

On 4 November 2026, the local-source build succeeded. A separate bounded public download of all six pinned files produced **exactly the same output bytes**. Offline validation passed these checks:

- Accepted plus quarantined rows equals raw rows for both projects.
- Monthly record counts match project totals; all 38 retail country counts also match.
- Retail monthly and country signed amounts reconcile exactly to **GBP 9,747,747.93**, and each month's positive plus signed negative amount equals its net.
- All 24 mobility civil-hour bins total **9,415,026 ordinary records**.
- Mobility monthly signed charges reconcile to **USD 256,598,279.23**; ordinary plus signed-adjustment values reconcile for each month.
- Monthly mobility quarantine counts total **2,857**; accepted record groups account for all **9,551,921** accepted records.
- December 2011 carries the partial-month flag. Two projects are locally published, three are queued, and neither claims an Azure deployment.

These are dashboard transformation/reconciliation checks. The underlying pipeline tests, full-source checks, limitations and recovery evidence remain in the linked project validation records.

## Attribution and reuse

Retail: **Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. DOI [10.24432/C5BW33](https://doi.org/10.24432/C5BW33)**, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The dashboard contains transformed and aggregated observations; no endorsement is implied.

Mobility: **NYC Taxi & Limousine Commission / NYC Open Data**, historical 2024 yellow-taxi records and the reviewed zone lookup, under the [NYC Open Data terms](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje). No Creative Commons licence or source-accuracy guarantee is invented. Original dashboard and builder code is covered by the repository's MIT licence; that does not relicense source data.
