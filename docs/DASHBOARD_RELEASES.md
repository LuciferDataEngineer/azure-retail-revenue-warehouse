# Add a published Azure project to the portfolio

The daily portfolio automation records each new project in this dashboard after its repository, tested commit and validation evidence are publicly readable. Its push triggers the existing Pages workflow. The next run can retry a pending dashboard update using the original project commit and Melbourne publication date.

## Project-side release record

Commit `examples/dashboard-release.json` to the publishing project before pushing it. Use these fields:

| Field | Contents |
| --- | --- |
| `schema_version` | Integer `1` |
| `project_id` | `energy`, `orders` or `inventory` |
| `coverage` | Source period and population, identifying synthetic events, fields or scenarios |
| `summary` | What the published implementation does |
| `stack` | List of implemented local tools |
| `tests_passed` | Observed passing local test count |
| `metrics` | One to four objects, each with a distinct text `label`, numeric `value` and text `unit`. Use aggregate observations supported by the evidence document. |
| `evidence_path` | Repository-relative path to the Markdown validation record, e.g. `docs/VALIDATION.md` |
| `cloud_status` | `not_deployed` for this locally validated series |

A commit cannot contain its own SHA. The release registration command receives the actual published SHA separately, and verifies the local release file byte for byte against that commit. It checks the expected public repository owner/name, fetches the linked validation document and records both file hashes. The roadmap stays in progress or queued until registration succeeds.

## Dashboard-side handoff

Run this from the **dashboard repository**. Set the shell variables to the actual release values. The publishing job must already have verified that the primary project CI passed for that commit.

```bash
python3 scripts/register_dashboard_release.py \
  --project "$PROJECT_ID" --commit "$PUBLISHED_SHA" \
  --published-on "$MELBOURNE_PUBLICATION_DATE" \
  --record "$PROJECT_DIRECTORY/examples/dashboard-release.json"

python3 scripts/build_dashboard_data.py --validate-only --verify-receipts
python3 scripts/build_dashboard_snapshot.py --check
python3 -m unittest tests.test_dashboard_publication
npm --prefix site ci
npm --prefix site run build
```

An identical retry leaves the receipt, cards and counts unchanged. A second, different release for the same initial publication raises a conflict so a later event cannot silently replace its history. Registration writes the receipt atomically. If rebuilding stops partway, rerun the same command. The Pages workflow checks consistency before deployment.

Review and commit the three outputs together: `site/portfolio/releases/<project_id>.json`, `site/data/dashboard.json` and `site/src/data.json`. Push normally to the dashboard's `main` branch. A non-fast-forward push needs a fresh copy of main and replay of the same registration, preserving other projects' updates.

Confirm the Pages workflow succeeded for the dashboard commit. Open the public portfolio and check the new project title, displayed measurements, pinned evidence link and updated project count. Record the dashboard commit and deployment URL in the local portfolio index/backlog. If Pages fails, keep the primary repository's publication and retry only its dashboard handoff.

The base planning states live in [roadmap.json](../site/portfolio/roadmap.json). Each verified receipt supersedes its planning state. Existing retail and mobility charts retain their original data periods. Additional project cards show their reviewed measurements and evidence as they are registered.
