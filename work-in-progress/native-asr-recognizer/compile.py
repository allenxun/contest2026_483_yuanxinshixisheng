import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent
gate=json.loads((r.parent/'native-asr-model-session/compile-result.json').read_text())
command=gate['command'][:]
command=[x for x in command if x!='-Werror']
command[command.index('-c')+1]=str(r/'online-paraformer-model.cc')
command[command.index('-o')+1]=str(r/'online-paraformer-model.cc.o')
command+=['-I'+str(r),'-DK7_ASR_NATIVE_STORAGE=1']
assert not (r/'compile-attempt2.json').exists()
result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(r/'compile-attempt2.log').write_bytes(result.stdout)
report={'exit_code':result.returncode,'command':command,'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.iterdir() if p.suffix in ('.cc','.hpp','.h','.py')},'firmware_integrated':False,'board_tested':False}
(r/'compile-attempt2.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'exit_code':result.returncode,'log_bytes':len(result.stdout)}))
