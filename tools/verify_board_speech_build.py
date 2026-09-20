import base64,json
from cloud_radio_stage_audit import ROOT,remote
rel='tests/k7cloud/test_board_speech_wire.c'
code='''import pathlib,base64,subprocess,json,hashlib
root=pathlib.Path('/home/swl/openvela/work/velavision-project');p=root/%r
p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(%r))
ev=root/'evidence/board-speech-bridge-20260914'
for opt in ['-O0','-O2']:
 binary=ev/('wire-test'+opt)
 subprocess.check_call(['gcc','-std=gnu11','-Wall','-Wextra','-Werror',opt,'-pthread','-I'+str(root/'app/k7sound'),str(p),str(root/'app/k7sound/stream_ring.c'),'-o',str(binary)])
 subprocess.check_call([str(binary)])
fw=pathlib.Path('/home/swl/openvela/cmake_out/velavision_board_speech_bridge_20260914/nuttx.bin').read_bytes()
result={'bytes':len(fw),'sha256':hashlib.sha256(fw).hexdigest(),'host_wire_tests':'O0/O2 pass','board_loaded':False}
(ev/'build-result.json').write_text(json.dumps(result))
print(json.dumps(result))
'''%(rel,base64.b64encode((ROOT/rel).read_bytes()).decode())
result=remote(code);(ROOT/'evidence/board-speech-bridge-20260914/verification.log').write_bytes(result)
print(result.decode())
