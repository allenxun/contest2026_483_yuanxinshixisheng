"""Build actual remaining sync target and NuttX localeconv in isolated scope."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-ort-support1';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-support1-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'support-attempt1';O.mkdir()
assert json.loads((S/'compile-attempt6/result.json').read_text())['exit_code']==0
cmd=['/dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake','--build',str(S/'build'),'--target','nsync_cpp','-j4']
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
(O/'nsync.log').write_bytes(q.stdout)
result=dict(nsync_exit=q.returncode,nsync_command=cmd,firmware_linked=False,model_run=False)
if q.returncode==0:
 source=Path('/home/swl/openvela/nuttx/libs/libc/locale/lib_localeconv.c')
 (O/source.name).write_bytes(source.read_bytes())
 base=json.loads(Path('/dev/shm/velavision-native-add-probe-20260911/result.json').read_text())['command']
 flags=base[:base.index('-c')]
 command=flags+['-DCONFIG_LIBC_LOCALE=1','-c',str(O/source.name),'-o',str(O/'localeconv.o')]
 p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
 (O/'localeconv.log').write_bytes(p.stdout)
 result.update(localeconv_exit=p.returncode,localeconv_command=command,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
 if p.returncode==0:
  ar=str(Path(base[0]).with_name('aarch64-none-elf-ar'))
  q=subprocess.run([ar,'rcs',str(O/'libk7_locale.a'),str(O/'localeconv.o')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  result['archive_exit']=q.returncode
  if q.returncode==0:result['archive_sha256']=hashlib.sha256((O/'libk7_locale.a').read_bytes()).hexdigest()
result['limitation']='Actual NuttX source with isolated locale define; formal firmware must use consistent locale configuration. Not a fake locale implementation.'
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for x in O.iterdir():
  if x.suffix in ('.json','.log','.c','.a'):t.add(x,arcname=x.name)
print(json.dumps(result),flush=True)
'''
(P/'build.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
subprocess.run(['scp.exe',*options,str(P/'build.py'),host+':'+dest+'/support.py'],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/support.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/support-attempt1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
