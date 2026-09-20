"""Keep native SDK warnings visible while avoiding vendor-only promotion."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-ort-session-warnings';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-session-warnings-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'warning-config';O.mkdir()
p=S/'ort/cmake/CMakeLists.txt';before=p.read_bytes();text=before.decode()
old='target_compile_definitions(${target_name} PRIVATE ORT_K7_NUTTX)'
new=old+'\n      # SDK warning categories are retained, but vendor code is not Werror-clean for these.\n      target_compile_options(${target_name} PRIVATE -Wno-error=shadow -Wno-error=undef)'
assert text.count(old)==1 and '-Wno-error=shadow' not in text
p.write_text(text.replace(old,new))
(O/'CMakeLists.before.txt').write_bytes(before);(O/'CMakeLists.after.txt').write_bytes(p.read_bytes())
record=json.loads((S/'config-attempt9/result.json').read_text())
cmd=next(x['command'] for x in record['records'] if x.get('name')=='configure')
cmd.append('-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(q.stdout)
(O/'result.json').write_text(json.dumps(dict(exit_code=q.returncode,command=cmd,before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest()),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as tar:
 for p in O.iterdir():
  if p.suffix in ('.json','.log','.txt'):tar.add(p,arcname=p.name)
print('CONFIG',q.returncode,flush=True)
print(q.stdout.decode(errors='replace')[-1600:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
def call(args):subprocess.run(args,check=True)
call(['scp.exe',*options,str(P/'configure.py'),host+':'+dest+'/warning-config.py'])
call(['ssh.exe',*options,host,'python3 '+dest+'/warning-config.py'])
call(['scp.exe',*options,host+':'+dest+'/warning-config/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
