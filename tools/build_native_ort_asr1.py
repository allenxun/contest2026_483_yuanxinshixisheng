"""Build configured real native runtime archives, preserving the first failure."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-ort-asr-build1';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-asr-build1-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile,time,os,signal
from pathlib import Path
S=Path('/home/swl/openvela/work/native-ort-asr-20260911');O=S/'compile-attempt1';O.mkdir()
targets=['onnxruntime_session','onnxruntime_mlas','onnxruntime_framework','onnxruntime_optimizer',
 'onnxruntime_providers','onnxruntime_graph','onnxruntime_util','onnxruntime_common','onnxruntime_flatbuffers','nsync_cpp']
cmd=['/dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake','--build',str(S/'build'),'--target',*targets,'-j4']
start=time.monotonic();code=None;timeout=False
try:
 with (O/'build.log').open('wb') as stream:
  p=subprocess.Popen(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=p.wait(timeout=2400)
  except subprocess.TimeoutExpired:
   timeout=True;os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
except subprocess.TimeoutExpired:timeout=True
result=dict(exit_code=code,timeout=timeout,seconds=time.monotonic()-start,command=cmd,linked=False,model_run=False,
 config_sha256=hashlib.sha256((S/'build/CMakeCache.txt').read_bytes()).hexdigest())
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as tar:
 for p in O.iterdir():
  if p.suffix in ('.log','.json'):tar.add(p,arcname=p.name)
 for name in ('compile_commands.json','CMakeCache.txt'):
  if (S/'build'/name).exists():tar.add(S/'build'/name,arcname=name)
print(json.dumps(result),flush=True)
print((O/'build.log').read_text(errors='replace')[-6500:],flush=True)
'''
(P/'build.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/native-ort-asr-20260911'
def call(args):subprocess.run(args,check=True)
call(['scp.exe',*options,str(P/'build.py'),host+':'+dest+'/build.py'])
call(['ssh.exe',*options,host,'python3 '+dest+'/build.py'])
call(['scp.exe',*options,host+':'+dest+'/compile-attempt1/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
