import base64
from cloud_radio_stage_audit import ROOT,remote
rel='tests/k7cloud/test_board_speech_live_posix.c'
code='''import pathlib,base64,subprocess
root=pathlib.Path('/home/swl/openvela/work/velavision-project');p=root/%r
p.write_bytes(base64.b64decode(%r))
binary=root/'evidence/board-speech-affinity-20260914/posix-live'
subprocess.check_call(['gcc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-pthread','-I'+str(root/'app/k7sound'),str(p),str(root/'app/k7sound/stream_ring.c'),'-o',str(binary)])
subprocess.check_call([str(binary)])
'''%(rel,base64.b64encode((ROOT/rel).read_bytes()).decode())
result=remote(code);(ROOT/'evidence/board-speech-affinity-20260914/posix-live.log').write_bytes(result)
print(result.decode())
