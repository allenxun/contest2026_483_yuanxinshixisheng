"""Apply reviewed staged patches and run actual offline native Session configure."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];P=R/'private/native-ort-session-config3';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-session-config31-20260911';O.mkdir(exist_ok=True)
C=R/'work-in-progress/parallel-model-reader-medium/native-ort-cmake-nuttx-v1'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()=='a1f3c57ecea2154525489297da4e21cdbfbe3ebc740241a034d10b640fcc42cb'
remote=r'''
import hashlib,json,shlex,subprocess,tarfile,os
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'config-attempt3';O.mkdir()
CMAKE='/dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake'
records=[]
def run(name,cmd,cwd):
 p=subprocess.run(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
 (O/(name+'.log')).write_bytes(p.stdout)
 records.append(dict(name=name,command=cmd,exit_code=p.returncode))
 print(name,p.returncode,flush=True)
 if p.returncode:print(p.stdout.decode(errors='replace')[-7000:],flush=True)
 return p.returncode==0
def patch(name,file,tree):
 data=file.read_bytes().replace(bytes([13,10]),bytes([10]))
 p=subprocess.run(['patch','--dry-run','-R','--binary','--ignore-whitespace','-p1'],input=data,cwd=tree,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (O/(name+'-already-applied.log')).write_bytes(p.stdout)
 if p.returncode:raise RuntimeError(p.stdout.decode())
 records.append(dict(name=name,mode='reverse dry-run verified earlier patch',patch_sha256=hashlib.sha256(data).hexdigest(),exit_code=0))
os.environ['PYTHONPATH']=str(S/'sources/flatbuffers/python')

try:
 patch('nuttx-cmake',S/'candidate.patch',S/'ort')
 for name,file in [('flatbuffers','flatbuffers/flatbuffers.patch'),('protobuf','protobuf/protobuf_cmake.patch'),('onnx','onnx/onnx.patch')]:
  patch(name,S/'ort/cmake/patches'/file,S/'sources'/name)
 original=Path('/dev/shm/velavision-static-deps4-20260911/toolchain.cmake').read_text()
 compiler='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-gcc'
 original+='\nset(CMAKE_ASM_COMPILER '+compiler+')\nset(CMAKE_ASM_FLAGS_INIT "-D__NuttX__ -march=armv8-a -mcpu=cortex-a53")\n'
 (S/'session-toolchain.cmake').write_text(original)
 good=run('reduce-ops',['python3',str(S/'ort/tools/ci_build/reduce_op_kernels.py'),str(S/'add-only.config'),
  '--cmake_build_dir',str(S/'build'),'--is_extended_minimal_build_or_higher'],S/'ort')
 if good:
  cmd=[CMAKE,'-S',str(S/'ort/cmake'),'-B',str(S/'build'),'-G','Ninja','-C',str(S/'initial-cache.cmake'),
   '-DCMAKE_TOOLCHAIN_FILE='+str(S/'session-toolchain.cmake'),'-DCMAKE_BUILD_TYPE=MinSizeRel',
   '-DONNX_CUSTOM_PROTOC_EXECUTABLE='+str(S/'sources/protoc_linux_x64/bin/protoc'),
   '-Donnxruntime_USE_PREINSTALLED_EIGEN=ON','-Deigen_SOURCE_PATH=/dev/shm/velavision-ort-env3-20260911/eigen']
  aliases={'GSL':'microsoft_gsl','NLOHMANN_JSON':'json'}
  for name in ('abseil_cpp','date','safeint','google_nsync','flatbuffers','mp11','onnx','protobuf','re2','utf8_range','GSL','NLOHMANN_JSON'):
   cmd.append('-DFETCHCONTENT_SOURCE_DIR_'+name.upper()+'='+str(S/'sources'/aliases.get(name,name)))
  run('configure',cmd,S/'ort')
except Exception as error:
 records.append(dict(error=str(error)));print(str(error),flush=True)
(O/'result.json').write_text(json.dumps(dict(records=records,linked=False,model_run=False),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as tar:
 for file in O.iterdir():
  if file.suffix in ('.log','.json'):tar.add(file,arcname=file.name)
 if (S/'build/CMakeCache.txt').exists():tar.add(S/'build/CMakeCache.txt',arcname='CMakeCache.txt')
'''
(P/'configure.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as tar:
 for name in ('candidate.patch','initial-cache.cmake'):tar.add(C/name,arcname=name)
 tar.add(R/'work-in-progress/parallel-model-reader-medium/native-ort-session-build-map-v1/add-only.config',arcname='add-only.config')
 tar.add(P/'configure.py',arcname='configure.py')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
def call(args):subprocess.run(args,check=True)
call(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/configure-stage.tar.gz'])
call(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf configure-stage.tar.gz && python3 configure.py'])
call(['scp.exe',*options,host+':'+dest+'/config-attempt3/results.tar.gz',str(P/'results.tar.gz')])
with tarfile.open(P/'results.tar.gz') as tar:
 for item in tar.getmembers():assert item.isfile() and '/' not in item.name and '\\' not in item.name
 tar.extractall(O,filter='data')
