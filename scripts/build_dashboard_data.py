#!/usr/bin/env python3
"""Build a reviewed, aggregate-only dashboard snapshot from pinned public evidence.

No API token, database, Azure service or third-party Python package is required.
Default mode fetches six small JSON files at immutable Git commits. --local-root
reads the same files from the portfolio directory and verifies the same hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

OWNER = "LuciferDataEngineer"
SNAPSHOT_DATE = "2026-11-04"
MAX_BYTES = 1_048_576
MAX_DOWNLOAD_SECONDS = 90
ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "retail": {
        "slug": "azure-retail-revenue-warehouse", "date": "2026-11-04",
        "commit": "06c9566611b3ff7c1dfd41c4b5abf21033db4499",
        "hashes": {
            "report": "2e220f67b96f49486ef77d6c933d9a625cd1313a4ab67783cec5408fbc30f5e1",
            "sql-results": "ecd68df86d41eb8299e0a28c9d78abc9c9c1eda05fdcc49759cc3cdad64b9a5e",
            "live-validation": "00ebb265c974d3fdadc5aaa89f241a1f79099816320b1ed371947ba8fb9d06d4",
        },
    },
    "mobility": {
        "slug": "azure-urban-mobility-lakehouse", "date": "2026-11-03",
        "commit": "ce32b70f83d6e8593cc2e768ae5ff95b28888a7b",
        "hashes": {
            "report": "1acfc1a7ccd715d7a9858e9276ba0d29e2fdbe9152b53b01a2ad5db56db2f0c5",
            "sql-results": "159f76f088388756e8768b4e01bce175ec1ad4ad955d4a798268cea8e6bc2927",
            "live-validation": "149dc3b2241a59704e132231345ebf8c47ef16a2b0a61d9eab0c07bb346282b2",
        },
    },
}


def money(value: Decimal | str | int) -> str:
    return format(Decimal(value).quantize(Decimal("0.01")), "f")


def total(rows: list[dict], key: str) -> Decimal:
    return sum((Decimal(str(row[key])) for row in rows), Decimal(0))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_inputs(local_root: Path | None) -> tuple[dict, list[dict]]:
    inputs, provenance = {}, []
    deadline = time.monotonic() + MAX_DOWNLOAD_SECONDS
    for project_id, project in PROJECTS.items():
        inputs[project_id] = {}
        for stem, expected_sha in project["hashes"].items():
            relative = f"examples/{stem}-{project['date']}.json"
            raw_url = f"https://raw.githubusercontent.com/{OWNER}/{project['slug']}/{project['commit']}/{relative}"
            if local_root is None:
                remaining = deadline - time.monotonic()
                require(remaining > 0, "Public-evidence download budget exceeded")
                request = urllib.request.Request(raw_url, headers={"User-Agent": "DataPortfolioDashboard/1.0"})
                with urllib.request.urlopen(request, timeout=min(15, remaining)) as response:
                    require(response.geturl().startswith("https://raw.githubusercontent.com/"), "Unexpected download destination")
                    raw = response.read(MAX_BYTES + 1)
            else:
                raw = (local_root / f"{project['date']}-{project['slug']}" / relative).read_bytes()
            require(len(raw) <= MAX_BYTES, f"Evidence exceeds byte limit: {relative}")
            actual_sha = hashlib.sha256(raw).hexdigest()
            require(actual_sha == expected_sha, f"Pinned evidence checksum changed: {project_id}/{relative}")
            inputs[project_id][stem] = json.loads(raw)
            provenance.append({
                "project": project_id, "file": relative, "commit": project["commit"],
                "sha256": actual_sha, "bytes": len(raw), "raw_url": raw_url,
                "url": f"https://github.com/{OWNER}/{project['slug']}/blob/{project['commit']}/{relative}",
            })
    return inputs, provenance


def links(project_id: str) -> dict:
    project = PROJECTS[project_id]
    repo = f"https://github.com/{OWNER}/{project['slug']}"
    base = f"{repo}/blob/{project['commit']}"
    return {"repo_url": repo, "evidence_url": f"{base}/docs/VALIDATION.md",
            "sources_url": f"{base}/docs/SOURCES.md", "readme_url": f"{base}/README.md",
            "azure_url": f"{base}/docs/AZURE.md", "commit": project["commit"]}


def build(inputs: dict, provenance: list[dict]) -> dict:
    rr, rs, rv = (inputs["retail"][key] for key in ("report", "sql-results", "live-validation"))
    mr, ms, mv = (inputs["mobility"][key] for key in ("report", "sql-results", "live-validation"))
    retail_monthly = [{
        "month": row["month"][:7], "accepted_rows": row["accepted_lines"],
        "observed_business_dates": row["observed_business_dates"],
        "positive_sales_gbp": row["positive_sales_gbp"],
        "negative_adjustments_gbp": row["negative_adjustments_gbp"],
        "net_revenue_gbp": row["net_revenue_gbp"], "partial": row["month"] == "2011-12-01",
    } for row in rs["query_2"]]
    retail_countries = [{"country": row["country"], "accepted_rows": row["accepted_lines"],
                         "net_revenue_gbp": row["net_revenue_gbp"],
                         "signed_adjustments_gbp": row["signed_adjustments_gbp"]} for row in rs["query_3"]]
    retail_totals = {**rr["totals"], "positive_sales_gbp": rr["totals"]["positive_sales"],
                     "negative_adjustments_gbp": rr["totals"]["negative_adjustments"],
                     "net_revenue_gbp": rr["totals"]["net_revenue"], "business_dates": rr["current_days"],
                     "countries": rv["dimension_counts"]["dim_country"], "missing_description_lines": 1454}
    retail_quality = [{"key": key, "label": label, "records": retail_totals[key], "kind": "retained_warning"}
                      for key, label in [
                          ("unknown_customer_lines", "Missing customer ID"),
                          ("candidate_duplicate_lines", "Candidate duplicate lines"),
                          ("zero_value_lines", "Zero-value lines"),
                          ("cancellation_sign_mismatch_lines", "Cancellation / quantity-sign mismatch"),
                          ("negative_price_lines", "Negative-price lines"),
                      ]]
    monthly_groups = defaultdict(list)
    for row in ms["query_2"]:
        monthly_groups[row["source_month"]].append(row)
    mobility_monthly = []
    for source in mr["sources"]:
        group = monthly_groups[source["source_month"]]
        ordinary = next(row for row in group if not row["negative_adjustment"])
        adjustment = next(row for row in group if row["negative_adjustment"])
        mobility_monthly.append({
            "month": source["source_month"], "raw_rows": source["raw_rows"],
            "accepted_rows": source["accepted_rows"], "quarantined_rows": source["quarantined_rows"],
            "ordinary_records": ordinary["records"], "negative_adjustment_rows": adjustment["records"],
            "ordinary_charges_usd": ordinary["signed_total_amount_usd"],
            "adjustment_charges_usd": adjustment["signed_total_amount_usd"],
            "signed_charges_usd": money(total(group, "signed_total_amount_usd")),
            "signed_fares_usd": money(total(group, "signed_fares_usd")), "partial": False,
        })
    mobility_totals = {**mr["totals"],
                       "ordinary_records": mr["totals"]["accepted_rows"] - mr["totals"]["negative_adjustment_rows"],
                       "signed_charges_usd": money(total(mobility_monthly, "signed_charges_usd")),
                       "signed_fares_usd": money(total(mobility_monthly, "signed_fares_usd")),
                       "ordinary_charges_usd": money(total(mobility_monthly, "ordinary_charges_usd")),
                       "adjustment_charges_usd": money(total(mobility_monthly, "adjustment_charges_usd"))}
    reasons = defaultdict(int)
    for row in mr["quality_reasons"]:
        reasons[row["reason"]] += row["row_count"]
    retail_links, mobility_links = links("retail"), links("mobility")
    projects = [
        {"id": "mobility", "order": 1, "title": "Urban Mobility Lakehouse", "status": "published_local",
         "pattern": "Medallion lakehouse", "published_on": "2026-11-03", "tests_passed": 43,
         "cloud_status": "not_deployed", **mobility_links,
         "stack": ["Python", "DuckDB", "PyArrow", "SQL"],
         "azure_target": ["Data Factory", "ADLS Gen2", "Azure Databricks", "Delta Lake", "Unity Catalog", "Databricks SQL", "Azure Monitor"],
         "summary": "Versioned taxi files become quality-checked Silver records and hourly Gold aggregates."},
        {"id": "retail", "order": 2, "title": "Retail Revenue Warehouse", "status": "published_local",
         "pattern": "Scheduled batch ELT", "published_on": "2026-11-04", "tests_passed": 42,
         "cloud_status": "not_deployed", **retail_links,
         "stack": ["Python", "DuckDB", "PyArrow", "openpyxl", "SQL"],
         "azure_target": ["Container Apps Job", "ADLS Gen2", "Data Factory", "Synapse dedicated SQL pool", "Azure Monitor"],
         "summary": "Historical invoice lines become replay-safe daily deliveries and a dimensional warehouse."},
        {"id": "energy", "order": 3, "title": "Live Energy Monitoring", "status": "queued", "cloud_status": "not_deployed",
         "pattern": "Stateful event-time streaming", "repo_url": None, "tests_passed": None,
         "azure_target": ["Event Hubs", "Stream Analytics", "Azure Data Explorer", "ADLS Gen2", "Azure Monitor"],
         "summary": "Planned: replay historical household measurements with explicitly synthetic delays and spikes."},
        {"id": "orders", "order": 4, "title": "Order Integration Middleware", "status": "queued", "cloud_status": "not_deployed",
         "pattern": "Event-driven messaging", "repo_url": None, "tests_passed": None,
         "azure_target": ["Event Grid", "Azure Functions", "Service Bus", "Logic Apps", "Table Storage"],
         "summary": "Planned: version-aware fulfillment and audit consumers with controlled dead-letter replay."},
        {"id": "inventory", "order": 5, "title": "Inventory Synchronization", "status": "queued", "cloud_status": "not_deployed",
         "pattern": "Change-feed current-state projection", "repo_url": None, "tests_passed": None,
         "azure_target": ["Cosmos DB", "Azure Functions", "Azure SQL", "App Service", "Application Insights"],
         "summary": "Planned: monotonic stock projections, soft deletes and outage reconciliation without full reloads."},
    ]
    data = {
        "schema_version": "portfolio-dashboard-v1", "snapshot_date": SNAPSHOT_DATE,
        "owner": OWNER, "is_live_feed": False,
        "portfolio": {"published_local": 2, "cloud_deployed": 0, "total_planned": 5,
                      "tests_passed": 85, "source_rows": retail_totals["raw_rows"] + mobility_totals["raw_rows"],
                      "projects": projects},
        "retail": {
            "title": "Retail Revenue Warehouse", "currency": "GBP", "unit": "transaction lines",
            "period": {"start": "2010-12-01", "end": "2011-12-09", "label": "Dec 2010 – 9 Dec 2011", "historical": True,
                       "note": "December 2011 is partial through the ninth. One retailer; no present-day market inference."},
            "totals": retail_totals, "monthly": retail_monthly, "countries": retail_countries,
            "top_products": rs["query_5"], "quality": retail_quality,
            "view_scope": {"monthly": "All accepted lines by invoice month; last month is partial.",
                           "countries": "All accepted lines across the complete source period; independent of month selection.",
                           "top_products": "Top 20 stock codes by full-period signed amount; includes administrative codes such as DOT and POST.",
                           "quality": "Overlapping retained warning counts, not rejected rows and not additive."},
            "definitions": {
                "net_revenue_gbp": "Sum of signed quantity × four-decimal unit price, rounded to pennies per line; not audited revenue, cash or profit.",
                "negative_adjustments_gbp": "Sum of negative rounded line amounts; no inferred links to original purchases.",
                "unknown_customer_lines": "Accepted lines whose customer identifier is absent; retained using an Unknown dimension member.",
                "candidate_duplicate_lines": "Additional occurrences of identical modeled values; retained, not proven duplicate business events.",
            },
            "validation": {"tests_passed": 42, "pipeline_tests": 37, "adapter_tests": 5,
                           "source_rows_reconciled": rv["physical_source_rows_exactly_accounted"],
                           "independent_daily_reconciliations": rv["independent_daily_decimal_reconciliations"],
                           "replayed_dates": rv["same_source_replayed_days"], "dimension_orphans": rv["dimension_orphans"],
                           "business_state_unchanged_on_replay": rv["business_fingerprints_unchanged"],
                           "cloud_deployed": False, "observed_on": "2026-11-04", **retail_links,
                           "ci_url": f"{retail_links['repo_url']}/actions/runs/41794551121", "ci_status": "success"},
            "sources": [{"title": "UCI Online Retail", "url": "https://archive.ics.uci.edu/dataset/352/online+retail",
                         "citation": "Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. DOI: 10.24432/C5BW33.",
                         "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
                         "accessed_on": "2026-11-04", "transformations": "Workbook normalized into daily deliveries and signed line, month, country and product aggregates."}],
        },
        "mobility": {
            "title": "Urban Mobility Lakehouse", "currency": "USD", "unit": "trip records",
            "period": {"start": "2024-01-01", "end": "2024-03-31", "label": "Jan – Mar 2024", "historical": True,
                       "note": "Three historical yellow-taxi source months; no live traffic feed or congestion-pricing impact estimate."},
            "totals": mobility_totals, "monthly": mobility_monthly,
            "hourly": [{"hour": row["civil_hour"], "records": row["records"], "mean_civil_duration_seconds": row["mean_civil_duration_seconds"]} for row in ms["query_4"]],
            "top_zones": [{"zone_id": row["pickup_zone_id"], "zone": row["Zone"], "borough": row["Borough"],
                           "records": row["records"], "signed_charges_usd": row["recorded_charges_usd"]} for row in ms["top_pickup_zones"]],
            "quality": [{"key": key, "label": key.replace("_", " ").capitalize(), "records": count, "kind": "quarantine_reason"} for key, count in sorted(reasons.items())],
            "view_scope": {"monthly": "All accepted records, with signed adjustments retained separately.",
                           "hourly": "Ordinary records only across Jan–Mar 2024: neither original fare nor total was negative. Recorded NYC civil hour, not UTC.",
                           "top_zones": "Top 10 by ordinary-record count across Jan–Mar 2024. Names use a November 2026 lookup snapshot.",
                           "quality": "Quarantine reason occurrences; a record can have multiple reasons. Do not infer mutually exclusive categories."},
            "definitions": {
                "signed_charges_usd": "Sum of recorded total_amount rounded to cents; excludes cash tips and does not measure profit or driver take-home pay.",
                "ordinary_records": "Accepted rows with neither original fare nor original total negative; not necessarily paid fares.",
                "negative_adjustment_rows": "Accepted records with either original fare or total negative; no cause inferred.",
                "mean_civil_duration_seconds": "Mean dropoff-minus-pickup wall-clock seconds; not precise elapsed time across daylight-saving transitions.",
            },
            "validation": {"tests_passed": 43, "pipeline_tests": 34, "parity_tests": 1, "cloud_contract_tests": 8,
                           "physical_row_conservation": mv["all_source_rows_partitioned_exactly_once"],
                           "signed_decimal_reconciliation": mv["signed_decimal_silver_gold_reconciled"],
                           "business_state_unchanged_on_replay": mv["business_table_fingerprints_unchanged"],
                           "replayed_source_files": mv["identical_source_replays"], "zone_join_unmatched_groups": ms["zone_join_validation"]["unmatched_hourly_groups"],
                           "cloud_deployed": False, "observed_on": "2026-11-03", **mobility_links,
                           "ci_url": f"{mobility_links['repo_url']}/actions/runs/41535530637", "ci_status": "success"},
            "sources": [{"title": "NYC TLC yellow-taxi trip records", "url": "https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
                         "citation": "NYC Taxi & Limousine Commission / NYC Open Data, January–March 2024 yellow-taxi records.",
                         "license": "NYC Open Data reuse terms; no CC licence asserted", "license_url": "https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje",
                         "accessed_on": "2026-11-03", "transformations": "Quality-checked records become signed monthly and ordinary-record civil-hour/zone aggregates."}],
        },
        "provenance": {"snapshot_policy": "Pinned published aggregate evidence. No row-level records, live feed, Azure runtime or private data.",
                       "inputs": provenance, "cloud_boundary": "Both implementations passed local checks. Azure deployment, security, performance and recovery have not been validated.",
                       "roadmap_as_of": SNAPSHOT_DATE},
    }
    validate(data)
    return data


def validate(data: dict) -> None:
    require(data["schema_version"] == "portfolio-dashboard-v1", "Unknown dashboard schema")
    r, m = data["retail"], data["mobility"]
    for project in [r, m]:
        t = project["totals"]
        require(t["raw_rows"] == t["accepted_rows"] + t["quarantined_rows"], "Physical row conservation failed")
        require(total(project["monthly"], "accepted_rows") == t["accepted_rows"], "Monthly row counts do not reconcile")
        require(not project["validation"]["cloud_deployed"], "Unexpected cloud validation claim")
    require(total(r["monthly"], "net_revenue_gbp") == Decimal(r["totals"]["net_revenue_gbp"]), "Retail monthly money mismatch")
    require(total(r["countries"], "net_revenue_gbp") == Decimal(r["totals"]["net_revenue_gbp"]), "Retail country money mismatch")
    require(total(r["countries"], "accepted_rows") == r["totals"]["accepted_rows"], "Retail country row mismatch")
    for row in r["monthly"]:
        require(Decimal(row["positive_sales_gbp"]) + Decimal(row["negative_adjustments_gbp"]) == Decimal(row["net_revenue_gbp"]), "Retail signed-money mismatch")
    require(r["monthly"][-1]["month"] == "2011-12" and r["monthly"][-1]["partial"], "Missing partial-month disclosure")
    require(total(m["hourly"], "records") == m["totals"]["ordinary_records"], "Hourly ordinary-record denominator mismatch")
    require(len(m["hourly"]) == 24 and {row["hour"] for row in m["hourly"]} == set(range(24)), "Hourly bins incomplete")
    require(total(m["monthly"], "signed_charges_usd") == Decimal(m["totals"]["signed_charges_usd"]), "Mobility monthly money mismatch")
    require(total(m["monthly"], "quarantined_rows") == m["totals"]["quarantined_rows"], "Mobility quarantine mismatch")
    for row in m["monthly"]:
        require(row["ordinary_records"] + row["negative_adjustment_rows"] == row["accepted_rows"], "Mobility adjustment conservation failed")
        require(Decimal(row["ordinary_charges_usd"]) + Decimal(row["adjustment_charges_usd"]) == Decimal(row["signed_charges_usd"]), "Mobility signed-money mismatch")
    require(sum(project.get("tests_passed") or 0 for project in data["portfolio"]["projects"]) == data["portfolio"]["tests_passed"], "Test count mismatch")
    require(sum(project["status"] == "published_local" for project in data["portfolio"]["projects"]) == 2, "Publication status mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-root", type=Path, help="Read identical pinned evidence from this portfolio directory instead of downloading")
    parser.add_argument("--output", type=Path, default=ROOT / "site/data/dashboard.json")
    parser.add_argument("--check", action="store_true", help="Rebuild and compare to the existing output, without writing")
    parser.add_argument("--validate-only", action="store_true", help="Offline conservation and scope checks on the committed bundle")
    args = parser.parse_args()
    if args.validate_only:
        validate(json.loads(args.output.read_text()))
        print("Dashboard bundle conservation, signed money and scope checks passed (offline).")
        return
    inputs, provenance = read_inputs(args.local_root)
    data = build(inputs, provenance)
    rendered = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        require(args.output.read_text() == rendered, "Dashboard bundle differs from pinned evidence")
        print("Dashboard bundle matches all six pinned evidence files.")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".json.tmp")
        temporary.write_text(rendered)
        temporary.replace(args.output)
        print(f"Wrote aggregate dashboard bundle: {args.output.name}")


if __name__ == "__main__":
    main()
