"""Install only frozen reviewed files after checking all old target hashes."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
SDK = Path('/home/swl/openvela')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

before = json.loads((HERE / 'before.json').read_text(encoding='utf-8-sig'))
with (HERE / 'sdk-audit.log').open('xb') as log:
    subprocess.run(['python3', str(PROJECT / 'tools/sync_sdk.py'), '--sdk', str(SDK), '--check'],
                   stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
pairs = []
for relative, digest in before.items():
    source = HERE / 'changed' / relative
    assert source.is_file(), relative
    project_target = PROJECT / relative
    assert sha(project_target) == digest, str(project_target)
    pairs.append((source, project_target))
    # Unit tests and public parser documentation are not SDK build inputs.
    sdk_relative = relative.replace('app/voicelink/', 'apps/examples/voicelink/', 1)
    sdk_relative = sdk_relative.replace('app/k7sound/', 'apps/examples/k7sound/', 1)
    target = SDK / sdk_relative
    if target.exists():
        assert sha(target) == digest, str(target)
        pairs.append((source, target))
for source, target in pairs:
    shutil.copyfile(source, target)
(HERE / 'sync-result.json').write_text(json.dumps({
    'checked_before': before, 'installed': {str(t): sha(t) for _, t in pairs}}, indent=2))
print('PASS checked and synchronized', len(pairs), 'targets')
