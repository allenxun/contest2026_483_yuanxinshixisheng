"""Preserve successful candidate and exact source hashes; never deploy it."""
import base64
import hashlib
import json
from cloud_radio_stage_audit import ROOT,remote
from audit_voice_mode_sdk import FILES

data=json.loads(remote('''import pathlib,hashlib,json,base64
sdk=pathlib.Path('/home/swl/openvela')
ev=sdk/'work/velavision-project/evidence/voice-mode-20260915'
assert (ev/'build.exit').read_text().strip()=='0'
build=sdk/'cmake_out/velavision_voice_mode_20260915'
raw=(build/'nuttx.bin').read_bytes()
assert b'VOICE SESSION ready mode=0' in raw and b'VOICE MODE requested=' in raw
sources={rel:hashlib.sha256((sdk/'apps/examples'/rel[4:]).read_bytes()).hexdigest() for rel in %r}
print(json.dumps({'image':base64.b64encode(raw).decode(),
 'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),'sources':sources,
 'log':(ev/'build.log').read_text(errors='replace')}))
'''% (FILES+['app/k7host/k7_track.c','app/k7sound/k7sound_main.c','app/k7agent/cloud/src/board_speech_bridge.c'])))
out=ROOT/'evidence/voice-mode-20260915'
raw=base64.b64decode(data.pop('image'));log=data.pop('log')
assert hashlib.sha256(raw).hexdigest()==data['sha256']
for rel,digest in data['sources'].items():
    assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest,rel
for name,content in [('nuttx.bin',raw),('build.log',log.encode())]:
    target=out/name
    if target.exists() and target.read_bytes()!=content:raise RuntimeError('Refuse overwrite '+name)
    target.write_bytes(content)
data.update(build_exit_code=0,ram_loaded=False,hardware_tested=False,
            python_tests=48,c_mode_tests=['O0','O2'],
            build_directory='/home/swl/openvela/cmake_out/velavision_voice_mode_20260915')
(out/'verification.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(data,indent=2))
