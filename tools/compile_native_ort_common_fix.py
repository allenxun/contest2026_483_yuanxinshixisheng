"""Recompile only the three failed common units; preserve first-pass evidence."""
import hashlib,json,subprocess,tarfile,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'work-in-progress/native-voice-sources'
P=R/'private/native-ort-common-fix';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-common-compile2-20260911';O.mkdir(exist_ok=True)
C=R/'work-in-progress/parallel-model-reader-medium/logging-nuttx-v1/logging.cc'
assert hashlib.sha256(C.read_bytes()).hexdigest()=='60d95dc30f3dbe0eb6fc7223a38dc9ba87ef5f6bcdc73d694e04d9c0094ecadf'
z=B/'deps/date.zip';meta=json.loads(z.with_suffix('.json').read_text())
assert hashlib.sha256(z.read_bytes()).hexdigest()==meta['sha256']
with zipfile.ZipFile(z) as archive:
 for member in archive.infolist():
  rel=Path(*member.filename.split('/')[1:]);assert not rel.is_absolute() and '..' not in rel.parts
  if member.is_dir():continue
  target=P/'date'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(member))
remote=r'''
import json,subprocess,time,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-common2-20260911')
prior=Path('/dev/shm/velavision-ort-common1-20260911')
headers=Path('/dev/shm/velavision-ort-env3-20260911/ort/onnxruntime/core/common')
results=[]
for i in (5,6,8):
 args=json.loads((prior/(str(i)+'.command.json')).read_text());cut=args.index('-c')
 source=S/'logging.cc' if i==5 else Path(args[cut+1])
 cmd=args[:cut]+['-I'+str(headers),'-I'+str(S/'date/include'),'-c',str(source),'-o',str(S/(str(i)+'.o'))]
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
 (S/(str(i)+'.log')).write_bytes(p.stdout);(S/(str(i)+'.command.json')).write_text(json.dumps(cmd))
 results.append(dict(source=str(source),exit_code=p.returncode,index=i));print(results[-1],flush=True)
(S/'result.json').write_text(json.dumps(dict(results=results,linked=False,hardware_tested=False),indent=2))
with tarfile.open(S/'results.tar.gz','w:gz') as tar:
 for p in S.iterdir():
  if p.suffix in ('.log','.json','.o'):tar.add(p,arcname=p.name)
'''
(P/'compile.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 tar.add(C,arcname='logging.cc');tar.add(P/'date',arcname='date');tar.add(P/'compile.py',arcname='compile.py')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-common2-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 compile.py'])
call(['scp.exe',*options,host+':'+dest+'/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
