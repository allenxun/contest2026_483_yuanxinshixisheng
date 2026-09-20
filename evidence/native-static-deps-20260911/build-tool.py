"""Build real static dependency targets in isolated VM tmpfs, no SDK mutation."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-model-reader-medium/native-static-deps-cmake-v1'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()=='f74d8f62797b010d0cca4676eba1d633db4c543900d7215bba5e15325d47586a'
for name,row in json.loads((C/'outputs.json').read_text()).items():assert hashlib.sha256((C/name).read_bytes()).hexdigest()==row['sha256']
P=R/'private/native-static-deps-stage';P.mkdir(exist_ok=True)
O=R/'evidence/native-static-deps-20260911';O.mkdir(exist_ok=True)
remote=r'''
import json,shlex,subprocess,hashlib,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-static-deps-20260911')
SDK=Path('/home/swl/openvela');B=Path('/dev/shm/velavision_audio_sound_20260910')
entries=json.loads((B/'compile_commands.json').read_text())
lines=['set(CMAKE_SYSTEM_NAME NuttX)','set(CMAKE_SYSTEM_PROCESSOR aarch64)',
 'set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)']
for language,suffix in [('C','/k7radio_main.c'),('CXX','/k7voice_main.cpp')]:
 entry=next(x for x in entries if x['file'].endswith(suffix))
 args=entry.get('arguments') or shlex.split(entry['command']);compiler=args[0];flags=[];i=1
 while i<len(args):
  a=args[i]
  if a in ('-o','-MF','-MT','-MQ'):i+=2;continue
  if a in ('-MD','-MMD','-c') or a==entry['file'] or a.startswith('-Dmain='):i+=1;continue
  flags.append(a);i+=1
 lines += ['set(CMAKE_'+language+'_COMPILER [=['+compiler+']=])',
           'set(CMAKE_'+language+'_FLAGS_INIT [=['+shlex.join(flags)+']=])']
(S/'toolchain.cmake').write_text('\n'.join(lines)+'\n')
commands={
 'configure':['cmake','-S',str(S),'-B',str(S/'build'),'-G','Ninja',
 '-DCMAKE_TOOLCHAIN_FILE='+str(S/'toolchain.cmake'),
 '-DK7_ABSEIL_SOURCE=/dev/shm/velavision-ort-env3-20260911/abseil_cpp',
 '-DK7_NSYNC_SOURCE=/dev/shm/velavision-ort-env3-20260911/google_nsync'],
 'build':['cmake','--build',str(S/'build'),'--target','k7_native_deps','-j2']}
results={}
for name,cmd in commands.items():
 shell='source /home/swl/openvela/build/envsetup.sh >/dev/null && '+shlex.join(cmd)
 p=subprocess.run(['bash','-c',shell],cwd=SDK,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
 (S/(name+'.log')).write_bytes(p.stdout);results[name]=dict(exit_code=p.returncode,command=cmd)
 print(name,p.returncode,flush=True)
 if p.returncode:print(p.stdout.decode(errors='replace')[-7000:],flush=True);break
results.update(linked=False,hardware_tested=False,thread_link_proven=False)
(S/'result.json').write_text(json.dumps(results,indent=2))
with tarfile.open(S/'results.tar.gz','w:gz') as tar:
 for p in S.iterdir():
  if p.suffix in ('.json','.log','.cmake'):tar.add(p,arcname=p.name)
 if (S/'build/CMakeCache.txt').exists():tar.add(S/'build/CMakeCache.txt',arcname='CMakeCache.txt')
'''
(P/'build.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 for name in ('CMakeLists.txt','ort-abseil-targets.cmake'):tar.add(C/name,arcname=name)
 tar.add(P/'build.py',arcname='build.py')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-static-deps-20260911'
def call(args):subprocess.run(args,check=True)
call(['ssh.exe',*options,host,'mkdir '+dest])
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 build.py'])
call(['scp.exe',*options,host+':'+dest+'/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
