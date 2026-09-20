"""Generate exact ASR registrations in a fresh native build, preserving Add build."""
import subprocess,tarfile,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-ort-asr';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-asr-config2-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile,os
from pathlib import Path
T=Path('/dev/shm/velavision-ort-session-20260911')
S=Path('/home/swl/openvela/work/native-ort-asr-20260911');B=S/'build';assert not B.exists()
O=S/'config2';O.mkdir()
os.environ['PYTHONPATH']=str(T/'sources/flatbuffers/python')
assert json.loads((T/'compile-attempt6/result.json').read_text())['exit_code']==0
config=S/'asr-required.config';assert 'StringNormalizer' not in config.read_text()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p):sha(p) for p in (T/'ort').rglob('*') if p.is_file() and '.git' not in p.parts}
(O/'source-inputs.json').write_text(json.dumps(inputs,indent=2))
cmd=['python3',str(T/'ort/tools/ci_build/reduce_op_kernels.py'),str(config),'--cmake_build_dir',str(B),'--is_extended_minimal_build_or_higher']
q=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(O/'generate.log').write_bytes(q.stdout);assert q.returncode==0,q.stdout[-3000:]
generated={str(p.relative_to(B)):sha(p) for p in (B/'op_reduction.generated').rglob('*') if p.is_file()}
cmake=json.loads((T/'locale-config2/result.json').read_text())['command']
cmake[cmake.index('-B')+1]=str(B)
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmake)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(q.stdout)
assert all(sha(Path(p))==v for p,v in inputs.items()),'source changed during configuration'
(O/'result.json').write_text(json.dumps(dict(exit_code=q.returncode,command=cmake,generator=cmd,config_sha256=sha(config),generated=generated,compiled=False,model_run=False),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.log','.json'):t.add(p,arcname=p.name)
 if (B/'CMakeCache.txt').exists():t.add(B/'CMakeCache.txt',arcname='CMakeCache.txt')
print('ASR_ORT_CONFIG',q.returncode,flush=True);print(q.stdout.decode(errors='replace')[-1800:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-ort-asr-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir -p '+dest+' && test ! -d '+dest+'/build'],check=True)
for p,n in [(P/'configure.py','configure.py'),(R/'evidence/native-speech-ort-conversion1-20260911/asr-required.config','asr-required.config')]:
 subprocess.run(['scp.exe',*options,str(p),host+':'+dest+'/'+n],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/configure.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/config2/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
