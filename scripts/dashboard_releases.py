"""Validated public release records for the Azure series dashboard."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

OWNER = "LuciferDataEngineer"
PORTFOLIO = Path(__file__).resolve().parents[1] / "site" / "portfolio"
REPOS = {
    "energy": "azure-live-energy-monitoring",
    "orders": "azure-order-integration-middleware",
    "inventory": "azure-inventory-synchronization",
}
PUBLIC_RECORD = "examples/dashboard-release.json"
RECORD_LIMIT = 16_384
RECORD_KEYS = {"schema_version", "project_id", "coverage", "summary", "stack", "tests_passed",
               "metrics", "evidence_path", "cloud_status"}
RECEIPT_KEYS = {"commit", "published_on", "evidence_sha256", "release_sha256", "release"}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def short_text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and value.strip() == value and value.isprintable()


def iso_day(value):
    check(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "Use an ISO publication date")
    date.fromisoformat(value)
    return value


def validate_release(record, project_id):
    check(isinstance(record, dict) and set(record) == RECORD_KEYS, "Unexpected or missing release fields")
    check(type(record["schema_version"]) is int and record["schema_version"] == 1, "Unsupported release schema")
    check(project_id in REPOS and record["project_id"] == project_id, "Release project does not match the expected repository")
    check(record["cloud_status"] == "not_deployed", "Local publication requires its actual cloud validation status")
    check(short_text(record["coverage"], 240) and short_text(record["summary"], 400), "Supply a single-line coverage and summary")
    stack = record["stack"]
    check(isinstance(stack, list) and 1 <= len(stack) <= 16 and all(short_text(s, 64) for s in stack),
          "Supply actual local stack names")
    check(type(record["tests_passed"]) is int and record["tests_passed"] > 0, "Supply the observed local test count")
    metrics = record["metrics"]
    check(isinstance(metrics, list) and 1 <= len(metrics) <= 4, "Supply one to four observed metrics")
    for m in metrics:
        check(isinstance(m, dict) and set(m) == {"label", "value", "unit"} and short_text(m["label"], 80)
              and short_text(m["unit"], 40), "Each observed metric requires a label, value and unit")
        value = m["value"]
        check(type(value) in (int, float) and abs(value) <= 2**53 - 1 and math.isfinite(value), "Unsupported numeric metric")
    check(len({m["label"] for m in metrics}) == len(metrics), "Duplicate metric label")
    evidence = record["evidence_path"]
    check(isinstance(evidence, str) and len(evidence) <= 256 and evidence.endswith(".md")
          and all(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part) for part in evidence.split("/")),
          "Evidence must be a safe repository-relative Markdown path")


def validate_receipt(receipt, project_id):
    check(isinstance(receipt, dict) and set(receipt) == RECEIPT_KEYS, "Invalid publication receipt")
    check(re.fullmatch(r"[0-9a-f]{40}", str(receipt["commit"])), "Expected a full Git commit SHA")
    for field in ("release_sha256", "evidence_sha256"):
        check(re.fullmatch(r"[0-9a-f]{64}", str(receipt[field])), f"Invalid {field}")
    iso_day(receipt["published_on"])
    validate_release(receipt["release"], project_id)


def public_bytes(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "DataPortfolioDashboard/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        check(response.status == 200 and response.geturl() == url, "Unexpected public evidence destination")
        raw = response.read(limit + 1)
    check(0 < len(raw) <= limit, "Public file is empty or exceeds the release limit")
    return raw


def verify_publication(project_id, commit, published_on, local_bytes=None, *, fetch=public_bytes):
    check(project_id in REPOS, "Unknown Azure series project")
    check(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "Expected a full Git commit SHA")
    iso_day(published_on)
    if local_bytes is not None:
        check(0 < len(local_bytes) <= RECORD_LIMIT, "Local release file is empty or too large")
        validate_release(json.loads(local_bytes), project_id)
    repo = f"{OWNER}/{REPOS[project_id]}"
    metadata = json.loads(fetch(f"https://api.github.com/repos/{repo}", 65_536))
    check(metadata.get("full_name") == repo and metadata.get("private") is False,
          "Repository is not the expected public GitHub repository")
    raw_base = f"https://raw.githubusercontent.com/{repo}/{commit}"
    public = fetch(f"{raw_base}/{PUBLIC_RECORD}", RECORD_LIMIT)
    if local_bytes is not None:
        check(public == local_bytes, "Reviewed local record differs from the published commit")
    release = json.loads(public)
    validate_release(release, project_id)
    evidence = fetch(f"{raw_base}/{release['evidence_path']}", 262_144)
    check(bool(evidence.decode("utf-8").strip()), "Published validation evidence is empty")
    return {"commit": commit, "published_on": published_on, "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "release_sha256": hashlib.sha256(public).hexdigest(), "release": release}


def verify_registered_publications(root=PORTFOLIO, *, fetch=public_bytes):
    for path in sorted((root / "releases").glob("*.json")):
        saved = json.loads(path.read_text())
        validate_receipt(saved, path.stem)
        confirmed = verify_publication(path.stem, saved["commit"], saved["published_on"], fetch=fetch)
        check(confirmed == saved, f"Receipt differs from public evidence: {path.stem}")


def register_receipt(receipt, root=PORTFOLIO):
    """First publication wins atomically. A repeated identical publication is a no-op."""
    project_id = receipt["release"]["project_id"]
    validate_receipt(receipt, project_id)
    directory = root / "releases"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{project_id}.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as staged:
        temporary = Path(staged.name)
        json.dump(receipt, staged, indent=2, ensure_ascii=False)
        staged.write("\n")
    try:
        try:
            os.link(temporary, target)
            return True
        except FileExistsError:
            check(json.loads(target.read_text()) == receipt, "A different publication is already registered for this project")
            return False
    finally:
        temporary.unlink(missing_ok=True)


def apply_publications(data, root=PORTFOLIO):
    roadmap = json.loads((root / "roadmap.json").read_text())
    check(set(roadmap) == set(REPOS), "Roadmap identities differ from the Azure series")
    directory = root / "releases"
    receipts = {p.stem: json.loads(p.read_text()) for p in directory.glob("*.json")}
    check(set(receipts) <= set(REPOS), "Unexpected project receipt")
    projects = data["portfolio"]["projects"]
    check(len(projects) == 5 and {p["id"] for p in projects} == {"retail", "mobility", *REPOS},
          "Expected five distinct roadmap projects")
    dates = []
    for project in projects:
        project_id = project["id"]
        if project_id not in REPOS:
            dates.append(iso_day(project["published_on"]))
            continue
        progress = roadmap[project_id]
        check(set(progress) == {"status", "updated_on"} and progress["status"] in ("queued", "in_progress"),
              "Unexpected roadmap state")
        dates.append(iso_day(progress["updated_on"]))
        project["status"] = progress["status"]
        if project_id not in receipts:
            check(not project.get("repo_url") and project.get("tests_passed") is None,
                  "Published card has no matching public receipt")
            continue
        receipt = receipts[project_id]
        validate_receipt(receipt, project_id)
        record = receipt["release"]
        repo_url = f"https://github.com/{OWNER}/{REPOS[project_id]}"
        pinned_url = f"{repo_url}/blob/{receipt['commit']}"
        project.update(status="published_local", published_on=receipt["published_on"], commit=receipt["commit"],
            repo_url=repo_url, evidence_url=f"{pinned_url}/{record['evidence_path']}",
            release_url=f"{pinned_url}/{PUBLIC_RECORD}", release_sha256=receipt["release_sha256"],
            evidence_sha256=receipt["evidence_sha256"],
            **{k: record[k] for k in ("cloud_status", "coverage", "summary", "stack", "tests_passed", "metrics")})
        dates.append(receipt["published_on"])
    published = [p for p in projects if p["status"] == "published_local"]
    data["portfolio"].update(published_local=len(published), total_planned=len(projects),
        cloud_deployed=sum(p["cloud_status"] == "deployed" for p in projects),
        tests_passed=sum(p["tests_passed"] for p in published))
    data["snapshot_date"] = data["provenance"]["roadmap_as_of"] = max(dates)
    data["provenance"]["cloud_boundary"] = "The published implementations have local validation evidence. Azure deployment and cloud validation remain pending."
    return data
