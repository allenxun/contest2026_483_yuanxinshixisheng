"""Exclude an unregistered locale kernel after checking actual reduced registrations."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-ort-reduced-locale2';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-reduced-locale2-20260911';O.mkdir(exist_ok=True)
C=R/'work-in-progress/parallel-model-reader-medium/native-iconv-reduced-v1'
remote=r'''
import hashlib,json,shlex,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'locale-config2';O.mkdir()
assert json.loads((S/'compile-attempt3/result.json').read_text())['exit_code']==1
registration=S/'build/op_reduction.generated/onnxruntime/core/providers/cpu/cpu_execution_provider.cc'
verifier=S/'k7_verify_no_string_normalizer.py'
q=subprocess.run(['python3',str(verifier),str(registration)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(O/'registration-check.log').write_bytes(q.stdout)
assert q.returncode==0,q.stdout
paths=[S/'ort/cmake/CMakeLists.txt',S/'ort/cmake/onnxruntime_providers_cpu.cmake']
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
for p in paths:(O/(p.name+'.before')).write_bytes(p.read_bytes())
for args in (['git','apply','--check',str(S/'reduced-locale.patch')],['git','apply',str(S/'reduced-locale.patch')]):
 q=subprocess.run(args,cwd=S/'ort',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 assert q.returncode==0,q.stdout
(S/'ort/cmake/k7_verify_no_string_normalizer.py').write_bytes(verifier.read_bytes())
record=json.loads((S/'cpu-flags-config/result.json').read_text())
cmd=record['command']
cmd.append('-DK7_NUTTX_REDUCED_NO_STRING_NORMALIZER=ON')
q=subprocess.run(['bash','-c','cd /home/swl/openvela && source build/envsetup.sh >/dev/null && '+shlex.join(cmd)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
(O/'configure.log').write_bytes(q.stdout)
result=dict(exit_code=q.returncode,command=cmd,before=before,
 after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
 registration_sha256=hashlib.sha256(registration.read_bytes()).hexdigest(),hardware_tested=False)
if q.returncode==0:
 commands=json.loads((S/'build/compile_commands.json').read_text())
 assert not any(x['file'].endswith('/string_normalizer.cc') for x in commands)
 result['string_normalizer_source_absent']=True
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.json','.log','.before'):t.add(p,arcname=p.name)
print(json.dumps(result),flush=True)
print(q.stdout.decode(errors='replace')[-1200:],flush=True)
'''
(P/'configure.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
(P/'reduced-locale.patch').write_text((C/'candidate.patch').read_text(),newline='\n')
for src,name in [(P/'configure.py','locale-config.py'),(P/'reduced-locale.patch','reduced-locale.patch'),(R/'work-in-progress/native-locale-registration-check/k7_verify_no_string_normalizer.py','k7_verify_no_string_normalizer.py')]:
 subprocess.run(['scp.exe',*options,str(src),host+':'+dest+'/'+name],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/locale-config.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/locale-config2/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
