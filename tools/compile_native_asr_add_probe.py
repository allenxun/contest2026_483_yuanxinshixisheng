"""Compile the real C API client with target headers; no fake C API or inference."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-asr-add-probe';P.mkdir(exist_ok=True)
O=R/'evidence/native-asr-add-probe-compile-20260911';O.mkdir(exist_ok=True)
C=R/'work-in-progress/native-ort-asr-add-probe'
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-native-asr-add-probe-20260911')
B=Path('/dev/shm/velavision_audio_sound_20260910')
entry=next(x for x in json.loads((B/'compile_commands.json').read_text()) if x['file'].endswith('/k7radio_main.c'))
args=entry.get('arguments') or shlex.split(entry['command']);flags=[];i=1
while i<len(args):
 a=args[i]
 if a in ('-o','-MF','-MT','-MQ'):i+=2;continue
 if a in ('-c','-MD','-MMD') or a==entry['file'] or a.startswith('-Dmain='):i+=1;continue
 flags.append(a);i+=1
cmd=[args[0],*flags,'-Werror','-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session',
 '-c',str(S/'add_probe.c'),'-o',str(S/'add_probe.o')]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
(S/'compile.log').write_bytes(p.stdout)
(S/'result.json').write_text(json.dumps(dict(exit_code=p.returncode,command=cmd,
 inputs={n:hashlib.sha256((S/n).read_bytes()).hexdigest() for n in ('add_probe.c','add_model.h','add.onnx')},
 linked=False,model_run=False),indent=2))
with tarfile.open(S/'results.tar.gz','w:gz') as tar:
 for file in S.iterdir():
  if file.suffix in ('.json','.log','.o'):tar.add(file,arcname=file.name)
print('PROBE_COMPILE',p.returncode,flush=True);print(p.stdout.decode(errors='replace')[-2000:],flush=True)
'''
(P/'compile.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 for name in ('add_probe.c','add_model.h','add.onnx'):tar.add(C/name,arcname=name)
 tar.add(P/'compile.py',arcname='compile.py')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-native-asr-add-probe-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 compile.py'])
call(['scp.exe',*options,host+':'+dest+'/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
