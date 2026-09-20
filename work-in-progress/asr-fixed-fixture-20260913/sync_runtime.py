import hashlib
import json
import subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
project = here.parents[1]
sdk = Path('/home/swl/openvela')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = here / 'runtime-after.cpp'
assert sha(source) == '4a976bb90e562ac034d81fc7c0a27c01d618086b491808082272b4fc894df93b'
targets = [project / 'app/voicelink/src/native_asr_runtime.cpp', sdk / 'apps/examples/voicelink/src/native_asr_runtime.cpp']
with (here / 'sdk-audit.log').open('xb') as output:
    subprocess.run(['python3', str(project / 'tools/sync_sdk.py'), '--sdk', str(sdk), '--check'], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)
for target in targets:
    assert sha(target) == 'ffa3d3542964fb25ebae4b6f9228b7ed100279105903f07982658ec0f838861e', str(target)
for target in targets:
    target.write_bytes(source.read_bytes())
(here / 'sync-result.json').write_text(json.dumps({str(p): sha(p) for p in targets}, indent=2))
