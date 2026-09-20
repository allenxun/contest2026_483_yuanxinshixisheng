import hashlib
import json
import subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
project = here.parents[1]
sdk = Path('/home/swl/openvela')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = here / 'k7sound_main.after.c'
assert sha(source) == 'ed52c6da0933172249ec80a794cd7ab74b0d9ccc581620a060eac5f05c4322e3'
targets = [project / 'app/k7sound/k7sound_main.c', sdk / 'apps/examples/k7sound/k7sound_main.c']
with (here / 'sdk-audit.log').open('xb') as output:
    subprocess.run(['python3', str(project / 'tools/sync_sdk.py'), '--sdk', str(sdk), '--check'], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)
for target in targets:
    assert sha(target) == 'cbbcc8a4f8a0a4b75dc99dcbf7c01c8a8d13a26a581bc1a18a7dc9281e6586da', str(target)
for target in targets:
    target.write_bytes(source.read_bytes())
(here / 'sync-result.json').write_text(json.dumps({str(p): sha(p) for p in targets}, indent=2))
