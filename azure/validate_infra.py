"""Compile templates offline, including deliberate rejection of production config."""
import json
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
json.loads((root/'azure/adf/publish-date.json').read_text())
with tempfile.TemporaryDirectory(prefix='retail-bicep-') as temp:
    for name in ['main','orchestration']:
        subprocess.run(['az','bicep','build','--file',str(root/f'infra/{name}.bicep'),
                        '--outfile',str(Path(temp)/f'{name}.json')],check=True)
    subprocess.run(['az','bicep','build-params','--file',str(root/'infra/dev.bicepparam'),
                    '--outfile',str(Path(temp)/'dev.json')],check=True)
    result=subprocess.run(['az','bicep','build-params','--file',str(root/'infra/prod.bicepparam'),
                           '--outfile',str(Path(temp)/'prod.json')],capture_output=True,text=True)
    if result.returncode==0 or 'BCP033' not in result.stderr or "'prod'" not in result.stderr:
        raise SystemExit('Production contract did not fail closed as expected')
print('PASS: 2 Bicep templates, dev parameters, JSON; production deliberately rejected')
