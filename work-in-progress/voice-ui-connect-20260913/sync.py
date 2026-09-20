import hashlib, json, subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
project = here.parents[1]
sdk = Path('/home/swl/openvela')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected = json.loads((here / 'inputs.json').read_text(encoding='utf-8-sig'))
with (here / 'sdk-audit.log').open('xb') as log:
    subprocess.run(['python3', str(project / 'tools/sync_sdk.py'), '--sdk', str(sdk), '--check'], stdout=log, stderr=subprocess.STDOUT, check=True)
pairs = []
for name in ('k7voice_main.cpp', 'ui_connect.hpp'):
    source = here / name
    assert sha(source) == expected['app/voicelink/src/' + name]
    for directory in (project / 'app/voicelink/src', sdk / 'apps/examples/voicelink/src'):
        target = directory / name
        if name == 'k7voice_main.cpp':
            assert sha(target) == '11da4cef7900527f868769d5c9e6dc82a13306d2bedb1d2dbaefb5e28baa9c6f'
        else:
            assert not target.exists()
        pairs.append((source, target))
for source, target in pairs:
    target.write_bytes(source.read_bytes())
