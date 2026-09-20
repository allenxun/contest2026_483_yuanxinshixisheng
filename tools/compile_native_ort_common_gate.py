"""Compile explicit ORT common/platform sources; no claim of library linkage."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
S=R/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'
P=R/'private/native-ort-common-stage';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-common-compile1-20260911';O.mkdir(exist_ok=True)
files=[]
for pattern in ('onnxruntime/core/common/*.cc','onnxruntime/core/common/logging/*.cc',
 'onnxruntime/core/common/logging/sinks/*.cc','onnxruntime/core/platform/*.cc',
 'onnxruntime/core/platform/posix/*.cc','onnxruntime/core/quantization/*.cc',
 'onnxruntime/core/platform/logging/make_platform_default_log_sink.cc'):
    files.extend(S.glob(pattern))
files=sorted(set(files))
manifest={p.relative_to(S).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(P/'sources.json').write_text(json.dumps(manifest,indent=2))
remote=r'''
import concurrent.futures,json,shlex,subprocess,time,hashlib
from pathlib import Path
S=Path('/dev/shm/velavision-ort-common1-20260911')
prior=Path('/dev/shm/velavision-ort-env3-20260911')
args=json.loads((prior/'command.json').read_text())
cut=args.index('-c');base=args[:cut]
sources=json.loads((S/'sources.json').read_text())
results=[]
def compile_one(pair):
 index,(rel,digest)=pair
 file=S/'ort'/rel
 assert hashlib.sha256(file.read_bytes()).hexdigest()==digest
 # Existing successfully compiled patched POSIX Env is separately accounted.
 if rel.endswith('/posix/env.cc'):return dict(source=rel,skipped='patched Env v2 compiled separately')
 # Keep copied input headers from prior immutable Env gate, and compile this source.
 command=base+['-c',str(file),'-o',str(S/(str(index)+'.o'))]
 start=time.monotonic()
 p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 (S/(str(index)+'.log')).write_bytes(p.stdout)
 (S/(str(index)+'.command.json')).write_text(json.dumps(command))
 result=dict(source=rel,exit_code=p.returncode,seconds=time.monotonic()-start,log=str(index)+'.log')
 print(json.dumps(result),flush=True)
 return result
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for row in pool.map(compile_one,enumerate(sources.items())):results.append(row)
(S/'result.json').write_text(json.dumps(dict(results=results,linked=False,hardware_tested=False,
 scope='explicit common/platform source compilation using prior native Env header environment'),indent=2))
import tarfile
with tarfile.open(S/'results.tar.gz','w:gz') as tar:
 for p in S.iterdir():
  if p.suffix in ('.json','.log','.o'):tar.add(p,arcname=p.name)
'''
(P/'compile.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
    for p in files:tar.add(p,arcname='ort/'+p.relative_to(S).as_posix())
    for name in ('sources.json','compile.py'):tar.add(P/name,arcname=name)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-common1-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 compile.py'])
call(['scp.exe',*options,host+':'+dest+'/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
    for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
    tar.extractall(O,filter='data')
print('Source compilation evidence:',O)
