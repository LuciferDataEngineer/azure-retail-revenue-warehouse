"""Bind the reviewed, pinned aggregate bundle to the dashboard's source inspector."""
import argparse
import json
from datetime import datetime, timezone
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
bundle = json.loads((ROOT / 'site/data/dashboard.json').read_text())
destination = ROOT / 'site/src/data.json'
previous = json.loads(destination.read_text())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Check the committed snapshot against the source bundle.')
args = parser.parse_args()
queries = {}

def add(query_id, rows, domain, scope, definitions=None):
    project = bundle[domain]
    sources = project['sources']
    inputs = [v for v in bundle['provenance']['inputs'] if v['project'] == domain]
    queries[query_id] = {
        'rows': rows,
        'source': {
            'name': project['title'],
            'provider': 'Published GitHub evidence',
            'period': project['period']['label'],
            'tables': [{'name': s['title'], 'href': s['url']} for s in sources]
                + [{'name': 'Validation and methods', 'href': project['validation']['evidence_url']}],
            'files': inputs,
            'caveats': [scope, project['period']['note'], 'Local results only. Azure has not been deployed or validated.'],
            'metricDefinitions': [{'label': k.replace('_', ' '), 'definition': v}
                for k, v in (definitions or project['definitions']).items()],
            'evidenceFlow': [
                {'title': 'Pinned published aggregates', 'detail': 'scripts/build_dashboard_data.py reads six immutable GitHub JSON artifacts, verifies SHA-256, and reconciles counts and exact Decimal money.'},
                {'title': 'Dashboard binding', 'detail': 'scripts/build_dashboard_snapshot.py preserves aggregate rows. Browser filters never query Azure or the raw datasets.'},
            ],
        },
        'methods': [{'language': 'text', 'code': 'Use the named arrays in site/data/dashboard.json without raw-row expansion. Chart money strings convert to numeric display values; summed money uses exact integer pennies/cents. Monthly filters apply only to the monthly section; other sections retain their stated full-period scope.'}],
    }

for domain in ('retail', 'mobility'):
    project = bundle[domain]
    add(domain + '_totals', [project['totals']], domain, 'Complete source period.')
    for collection in ('monthly', 'countries', 'top_products', 'hourly', 'top_zones', 'quality'):
        if collection in project:
            add(domain + '_' + collection, project[collection], domain, project['view_scope'][collection])
    add(domain + '_validation', [project['validation']], domain, 'Observed local checks; cloud checks have not run.')

queries['portfolio'] = {
    'rows': bundle['portfolio']['projects'],
    'source': {
        'name': 'Azure portfolio delivery record',
        'provider': 'Published repositories and approved project backlog',
        'period': 'As of ' + bundle['snapshot_date'],
        'tables': [{'name': p['title'], 'href': p['evidence_url']}
                   for p in bundle['portfolio']['projects'] if p.get('evidence_url')],
        'caveats': ['Published projects have local validation evidence. Cloud deployment remains pending.'],
        'metricDefinitions': [{'label': 'Local tests', 'definition': 'Sum of the observed local test counts in the published project records.'}],
        'evidenceFlow': [{'title': 'Delivery snapshot', 'detail': 'The source-controlled roadmap and pinned publication receipts determine project status. Only published implementations contribute local test counts.'}],
    },
}
snapshot = {
    'id': previous['id'], 'surface': 'dashboard', 'title': 'Data engineering portfolio',
    'generatedAt': previous['generatedAt'], 'buildStatus': 'complete',
    'filters': [], 'queries': queries,
    'portfolioSummary': bundle['portfolio'],
    'projectMetadata': {k: {v: bundle[k][v] for v in ('title', 'period', 'validation', 'sources', 'view_scope')}
                        for k in ('retail', 'mobility')},
    'exportPreferences': {'selected': None, 'destinations': []},
}
if args.check:
    if previous != snapshot:
        raise SystemExit('Displayed snapshot differs from the reviewed bundle. Regenerate it before deploying.')
elif previous != snapshot:
    snapshot['generatedAt'] = datetime.now(timezone.utc).isoformat()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as temporary:
        temporary.write(json.dumps(snapshot, indent=2) + '\n')
    Path(temporary.name).replace(destination)
print(f'Bound {len(queries)} reviewed queries; preserved dashboard identity {snapshot["id"]}.')
