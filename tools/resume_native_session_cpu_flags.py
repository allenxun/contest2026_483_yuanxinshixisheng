"""Separate baseline ISA from tuning; keep vendor per-file ISA dispatch intact."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-ort-cpu-flags';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-cpu-flags-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'cpu-flags-config';O.mkdir()
cache=(S/'build/CMakeCache.txt').read_text();changes={}
for key in ('CMAKE_C_FLAGS','CMAKE_CXX_FLAGS','CMAKE_ASM_FLAGS'):
 line=next(x for x in cache.splitlines() if x.startswith(key+':STRING='))
 old=line.split('=',1)[1];assert '-mcpu=cortex-a53' in old
 new=old.replace('-mcpu=cortex-a53','-mtune=cortex-a53')
 assert '-march=armv8-a' in new
 changes[key]=dict(before=old,after=new)
toolchain=S/'session-toolchain.cmake';before=toolchain.read_bytes()
toolchain.write_bytes(before.replace(b'-mcpu=cortex-a53',b'-mtune=cortex-a53'))
gcc='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-gcc'
macros=subprocess.check_output([gcc,'-march=armv8-a','-mtune=cortex-a53','-dM','-E','-x','c','/dev/null'],text=True)
(O/'baseline-macros.txt').write_text(macros)
for name in ('__ARM_FEATURE_DOTPROD','__ARM_FEATURE_FP16_VECTOR_ARITHMETIC','__ARM_FEATURE_BF16_VECTOR_ARITHMETIC'):
 assert '#define '+name+' ' not in macros,name
cmd=json.loads((S/'warning-config/result.json').read_text())['command']
cmd += ['-D'+key+'='+row['after'] for key,row in changes.items()]
cmd += ['-Donnxruntime_ENABLE_CPUINFO=OFF']
p=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(p.stdout)
(O/'result.json').write_text(json.dumps(dict(exit_code=p.returncode,command=cmd,changes=changes,baseline_has_extensions=False,
 toolchain_before=hashlib.sha256(before).hexdigest(),toolchain_after=hashlib.sha256(toolchain.read_bytes()).hexdigest()),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as tar:
 for f in O.iterdir():
  if f.suffix in ('.json','.txt','.log'):tar.add(f,arcname=f.name)
print('CONFIG',p.returncode,flush=True)
if p.returncode:print(p.stdout.decode(errors='replace')[-2000:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
def call(args):subprocess.run(args,check=True)
call(['scp.exe',*options,str(P/'configure.py'),host+':'+dest+'/cpu-flags-config.py'])
call(['ssh.exe',*options,host,'python3 '+dest+'/cpu-flags-config.py'])
call(['scp.exe',*options,host+':'+dest+'/cpu-flags-config/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
