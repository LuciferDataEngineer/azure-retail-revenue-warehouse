"""Offline release contract, replay, UI evidence and registry consistency."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dashboard_releases as releases
from build_dashboard_data import validate


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "roadmap.json").write_text(json.dumps({
            pid: {"status": "in_progress" if pid == "energy" else "queued", "updated_on": "2026-11-09"}
            for pid in releases.REPOS
        }))
        # Tests retain the real analytical aggregates, resetting only synthetic publication state.
        self.data = json.loads((ROOT / "site/data/dashboard.json").read_text())
        for project in self.data["portfolio"]["projects"]:
            if project["id"] in releases.REPOS:
                project.update(repo_url=None, tests_passed=None, status="queued")

    def receipt(self, pid, **override):
        manifest = {"schema_version": 1, "project_id": pid, "summary": "Synthetic test release",
                    "coverage": "Synthetic fixture replay", "stack": ["Python"], "tests_passed": 3,
                    "metrics": [{"label": "Processed events", "value": 12, "unit": "fixture events"}],
                    "evidence_path": "docs/VALIDATION.md", "cloud_status": "not_deployed", **override}
        raw = json.dumps(manifest).encode()
        slug = releases.REPOS[pid]
        commit = "a" * 40
        urls = {
            f"https://api.github.com/repos/LuciferDataEngineer/{slug}": json.dumps(
                {"full_name": f"LuciferDataEngineer/{slug}", "private": False}).encode(),
            f"https://raw.githubusercontent.com/LuciferDataEngineer/{slug}/{commit}/examples/dashboard-release.json": raw,
            f"https://raw.githubusercontent.com/LuciferDataEngineer/{slug}/{commit}/docs/VALIDATION.md": b"Fixture validation.",
        }
        return releases.verify_publication(pid, commit, "2026-11-10", raw, fetch=lambda url, _: urls[url])

    def test_all_three_publications_transition_without_new_explorer_queries(self):
        for offset, pid in enumerate(releases.REPOS, start=1):
            receipt = self.receipt(pid)
            self.assertTrue(releases.register_receipt(receipt, self.root))
            self.assertFalse(releases.register_receipt(receipt, self.root))
            data = releases.apply_publications(copy.deepcopy(self.data), self.root)
            validate(data, self.root)
            self.assertEqual(data["portfolio"]["published_local"], 2 + offset)
            self.assertEqual(data["portfolio"]["tests_passed"], 85 + 3 * offset)
            project = next(p for p in data["portfolio"]["projects"] if p["id"] == pid)
            self.assertEqual(project["metrics"], receipt["release"]["metrics"])
            self.assertIn(f"/blob/{receipt['commit']}/", project["evidence_url"])
            self.assertEqual(data["provenance"]["roadmap_as_of"], "2026-11-10")
            self.assertEqual(data["retail"], self.data["retail"])
            self.assertEqual(data["mobility"], self.data["mobility"])
            self.assertEqual(releases.apply_publications(copy.deepcopy(data), self.root), data)

    def test_progress_has_no_repository_before_publication(self):
        data = releases.apply_publications(self.data, self.root)
        project = next(p for p in data["portfolio"]["projects"] if p["id"] == "energy")
        self.assertEqual(project["status"], "in_progress")
        self.assertIsNone(project["repo_url"])
        self.assertEqual(data["portfolio"]["published_local"], 2)

    def test_replay_refuses_a_different_digest_or_metrics_for_same_project(self):
        receipt = self.receipt("energy")
        releases.register_receipt(receipt, self.root)
        changed = self.receipt("energy", tests_passed=4)
        with self.assertRaisesRegex(ValueError, "different publication"):
            releases.register_receipt(changed, self.root)
        path = self.root / "releases/energy.json"
        self.assertEqual(json.loads(path.read_text()), receipt)

    def test_rejects_unverified_links_or_asserted_cloud_completion(self):
        for path in ["../secret.md", "https://example.com/report.md", "/README.md", "%2e%2e/evidence.md"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.receipt("energy", evidence_path=path)
        with self.assertRaises(ValueError):
            self.receipt("energy", cloud_status="deployed")
        with self.assertRaises(ValueError):
            self.receipt("energy", metrics=[{"label": "Events", "value": float("nan"), "unit": "events"}])

    def test_nonmatching_public_record_cannot_be_registered(self):
        manifest = self.receipt("energy")["release"]
        def fetch(url, _):
            if "api.github.com" in url:
                return b'{"full_name":"LuciferDataEngineer/azure-live-energy-monitoring","private":false}'
            return b"{}"
        with self.assertRaisesRegex(ValueError, "differs"):
            releases.verify_publication("energy", "b" * 40, "2026-11-10", json.dumps(manifest).encode(), fetch=fetch)
        self.assertFalse((self.root / "releases").exists())
