"""Transfer reviewed config2 candidate and exact corrected dependencies."""
import hashlib,json,subprocess,tarfile,shlex
from pathlib import Path
R=Path(__file__).resolve().parents[1]
A=R/'work-in-progress/parallel-model-reader-medium'
D=A/'native-sherpa-config2-driver-v1';V=A/'native-sherpa-offline-stage-v3'
P=R/'private/native-sherpa-config2';P.mkdir(exist_ok=True)
O=R/'evidence/native-sherpa-asr-config2-20260911';O.mkdir(exist_ok=True)
assert not (O/'result.json').exists(), 'Do not overwrite a completed configuration'
manifest=json.loads((V/'source-manifest.json').read_text())
with tarfile.open(P/'stage.tar.gz','w:gz') as t:
 for p in D.iterdir():
  if p.is_file():t.add(p,arcname='driver/'+p.name)
 for rel,v in manifest.items():
  rel=rel.replace('\\','/')
  if not rel.startswith(('sources/kaldifst/','sources/openfst/')):continue
  p=V/rel;assert hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256']
  info=t.gettarinfo(str(p),arcname=rel);info.mode=int(v['mode'],8)
  with p.open('rb') as f:t.addfile(info,f)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-sherpa-config2-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir -p '+dest+' && test ! -d '+dest+'/result'],check=True)
subprocess.run(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'],check=True)
cmd=['python3',dest+'/driver/configure_config2.py','--stage','/dev/shm/velavision-sherpa-asr-20260911',
 '--corrected',dest+'/sources','--ort','/dev/shm/velavision-ort-session-20260911',
 '--build',dest+'/build','--output',dest+'/result','--cmake','/dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake',
 '--ninja','/home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja','--execute']
q=subprocess.run(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && cd /home/swl/openvela && . build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(O/('driver-'+str(len(list(O.glob('driver*.log'))))+'.log')).write_bytes(q.stdout);print('CONFIG2',q.returncode,flush=True)
for n in ('configure.log','result.json','inputs.json'):
 subprocess.run(['scp.exe',*options,host+':'+dest+'/result/'+n,str(O/n)],check=True)
for n in ('CMakeCache.txt','CMakeFiles/CMakeConfigureLog.yaml'):
 subprocess.run(['scp.exe',*options,host+':'+dest+'/build/'+n,str(O/Path(n).name)],check=True)
print((O/'configure.log').read_text(errors='replace')[-3500:])
