"""Compile the reviewed audio bridge with the real native ASR toolchain."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];C=R/'work-in-progress/native-shared-runtime-target'
P=R/'private/native-shared-runtime-target';P.mkdir(exist_ok=True)
O=R/'evidence/native-shared-runtime-target-compile1-20260911';O.mkdir(exist_ok=True)
files=['target_port.cpp','shared_runtime.hpp','k7_model_arena.h']
manifest={n:hashlib.sha256((C/n).read_bytes()).hexdigest() for n in files}
(P/'inputs.json').write_text(json.dumps(manifest,indent=2))
remote=r'''
import hashlib,json,shlex,subprocess,struct
from pathlib import Path
S=Path('/home/swl/openvela/work/native-shared-runtime-target-20260911')
inputs=json.loads((S/'inputs.json').read_text())
for n,h in inputs.items():assert hashlib.sha256((S/n).read_bytes()).hexdigest()==h
commands=json.loads(Path('/home/swl/openvela/work/native-sherpa-config2-20260911/build/compile_commands.json').read_text())
r=next(x for x in commands if x['file'].endswith('/sherpa-onnx/c-api/c-api.cc'))
cmd=shlex.split(r['command']);cmd[cmd.index('-o')+1]=str(S/'target_port.o');cmd[cmd.index('-c')+1]=str(S/'target_port.cpp')
cmd+=['-I'+str(S),'-Werror']
q=subprocess.run(cmd,cwd=r['directory'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(S/'compile.log').write_bytes(q.stdout)
result=dict(exit_code=q.returncode,command=cmd,inputs=inputs,linked=False,hardware_tested=False)
if q.returncode==0:
 b=(S/'target_port.o').read_bytes();assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
 result['object_sha256']=hashlib.sha256(b).hexdigest()
(S/'result.json').write_text(json.dumps(result,indent=2));print('SHARED_RUNTIME_COMPILE',q.returncode,flush=True)
print(q.stdout.decode(errors='replace')[-1800:])
'''
(P/'compile.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as t:
 for n in files:t.add(C/n,arcname=n)
 for n in ('inputs.json','compile.py'):t.add(P/n,arcname=n)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-shared-runtime-target-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir '+dest],check=True)
subprocess.run(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'],check=True)
subprocess.run(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 compile.py'],check=True)
for n in ('result.json','compile.log'):
 subprocess.run(['scp.exe',*options,host+':'+dest+'/'+n,str(O/n)],check=True)
