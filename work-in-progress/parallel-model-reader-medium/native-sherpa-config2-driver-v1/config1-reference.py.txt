"""Configure real ASR-only native sources with the completed ORT archive closure."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-sherpa-asr-config1';P.mkdir(exist_ok=True)
O=R/'evidence/native-sherpa-asr-config1-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-sherpa-asr-20260911')
T=Path('/dev/shm/velavision-ort-session-20260911')
assert json.loads((T/'compile-attempt6/result.json').read_text())['exit_code']==0
O=S/'config-attempt1';O.mkdir()
archives=sorted((T/'build').rglob('*.a'))
assert any(x.name=='libonnxruntime_session.a' for x in archives)
cmd=['/dev/shm/cmake-3.28.3-linux-x86_64/bin/cmake','-S',str(S/'sherpa'),'-B',str(S/'build'),'-G','Ninja',
 '-DK7_SHERPA_DEPS_ROOT='+str(S/'sources'),'-C',str(S/'candidate/asr-initial-cache.cmake'),
 '-DCMAKE_TOOLCHAIN_FILE='+str(T/'session-toolchain.cmake'),'-DCMAKE_BUILD_TYPE=MinSizeRel',
 '-DCMAKE_MAKE_PROGRAM=/home/swl/openvela/prebuilts/build-tools/linux-x86_64/bin/ninja',
 '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
 '-DK7_ORT_PUBLIC_INCLUDE_DIR='+str(T/'ort/include/onnxruntime/core/session'),
 '-DK7_ORT_STATIC_LIBRARIES='+';'.join(str(x) for x in archives)]
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],
 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(q.stdout)
(O/'result.json').write_text(json.dumps(dict(exit_code=q.returncode,command=cmd,
 archives=[dict(path=str(x),sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in archives],
 compiled=False,model_run=False),indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.json','.log'):t.add(p,arcname=p.name)
 if (S/'build/CMakeCache.txt').exists():t.add(S/'build/CMakeCache.txt',arcname='CMakeCache.txt')
print('SHERPA_CONFIG',q.returncode,flush=True)
print(q.stdout.decode(errors='replace')[-4000:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-sherpa-asr-20260911'
subprocess.run(['scp.exe',*options,str(P/'configure.py'),host+':'+dest+'/configure.py'],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/configure.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/config-attempt1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
