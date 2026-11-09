# Portfolio dashboard on GitHub Pages

The dashboard presents reviewed aggregate results from the Retail Revenue Warehouse and Urban Mobility Lakehouse, with the five-project Azure roadmap. Its GitHub Pages address is

**https://luciferdataengineer.github.io/azure-retail-revenue-warehouse/**

This is a static website. It does not connect to Azure, run a database, fetch live retail transactions or claim that the Azure projects are deployed. Historical source periods and observed local validation dates remain distinct. Only the reviewed public dashboard bundle is uploaded; workbook bytes, row-level records, local databases and workspace files are outside the published artifact.

## Build locally

Use Node.js 24 or a compatible newer version. From the repository root:

```bash
python3 scripts/build_dashboard_data.py --validate-only
python3 scripts/build_dashboard_snapshot.py --check
cd site
npm ci
npm run build
python3 -m http.server 4173 --directory dist
```

Open `http://localhost:4173/`. The build output is `site/dist/index.html`. The dependency lockfile is committed; generated dependencies and build output are excluded from source control.

The data is a reviewed snapshot of the projects' published evidence, not a continuously updated feed. See [DASHBOARD_DATA.md](DASHBOARD_DATA.md) for the source commits, transformation/reconciliation rules and refresh procedure. After reviewing updated evidence, run `python3 scripts/build_dashboard_data.py` followed by `python3 scripts/build_dashboard_snapshot.py` before committing both snapshots. Refreshing the data requires rebuilding and publishing the website; a visit does not execute an ETL pipeline.

## Deployment behavior

[The Pages workflow](../.github/workflows/pages.yml) builds on relevant pushes to `main`, pull requests and manual dispatch. Relevant paths are `site/**`, the dashboard data-builder script and the workflow itself. The build checks that the display snapshot matches the reviewed aggregate bundle. A successful build on `main` uploads and deploys the Pages artifact. Pull requests build without deployment. There is no recurring refresh schedule.

The build job has read permissions. The separate deployment job has `pages: write` and `id-token: write`, uses the `github-pages` environment and receives a short-lived GitHub identity token. No personal access token, Azure credential or repository secret is required by this workflow. Its artifact path is limited to `site/dist`.

One-time repository setup, when Pages has not yet been enabled:

```bash
gh api --method POST \
  repos/LuciferDataEngineer/azure-retail-revenue-warehouse/pages \
  -f build_type=workflow
```

That command changes the repository's Pages configuration and requires an authorized account with permission to manage it. It is a setup operation, not part of local builds. If a site already exists, inspect its settings before changing them; do not create another site or replace an existing custom domain blindly.

After a reviewed change is pushed to `main`, inspect the **Publish portfolio dashboard** Actions run. A successful deployment returns the actual URL. A manual redeployment uses:

```bash
gh workflow run pages.yml --ref main \
  --repo LuciferDataEngineer/azure-retail-revenue-warehouse
```

Confirm the deployment job succeeded and the public page loads before reporting publication. A successful application build alone does not establish that hosting succeeded.

## Recovery and maintenance

If a build fails, GitHub Pages retains the last successful deployment. Read the failed job, correct the source and push again. For a bad published change, revert that specific reviewed site commit and let the workflow publish the corrected source. Do not force-push unrelated project history. Deployment concurrency avoids cancelling an active publication halfway through.

The four portfolio charts use locally bundled Recharts. Each chart has keyboard-accessible exact values. The production dashboard uses the public reader mode.

The default GitHub Pages domain requires no domain purchase. GitHub documents Pages availability for public repositories on GitHub Free. No Azure resources are involved. Custom domains or other paid services are outside this implementation.

Action references were checked against their upstream release tags on 4 November 2026 and are pinned to full commit SHAs: checkout v7.0.1, setup-node v7.1.0, configure-pages v6.0.0, upload-pages-artifact v5.0.0 and deploy-pages v5.0.1. Review updates deliberately rather than changing hashes without checking their releases.

Primary references: [custom Pages workflows and permissions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Pages configuration API](https://docs.github.com/en/rest/pages/pages#create-a-github-pages-site), and the [official deployment action](https://github.com/actions/deploy-pages).
