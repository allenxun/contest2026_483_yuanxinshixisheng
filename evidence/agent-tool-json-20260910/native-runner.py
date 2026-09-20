
import hashlib,json,shlex,subprocess
from pathlib import Path
S=Path(__file__).resolve().parent;O=S/'result';O.mkdir()
for p,h in json.loads((S/'inputs.json').read_text()).items():assert hashlib.sha256((S/p).read_bytes()).hexdigest()==h
B=Path('/home/swl/openvela/cmake_out/velavision_cxx_eh_20260910')
db=json.loads((B/'compile_commands.json').read_text())
u=next(x for x in db if x['file'].endswith('/k7eh_main.cxx'))
argv=shlex.split(u['command']);cmd=[];i=0
while i<len(argv):
 a=argv[i];i+=1
 if a in ['-o','-MF','-MT','-MQ']:i+=1;continue
 if a in ['-MD','-MMD','-c'] or a.startswith('-Dmain=') or a==u['file']:continue
 cmd.append(a)
cmd+=['-Werror','-fdiagnostics-color=never','-I'+str(S),'-c',str(S/'tool_json.cpp'),'-o',str(O/'tool_json.o')]
p=subprocess.run(cmd,cwd=u['directory'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
(O/'native.log').write_bytes(p.stdout)
report=dict(command=cmd,exit_code=p.returncode,config_sha256=hashlib.sha256((B/'.config').read_bytes()).hexdigest(),
 scope='Real ARM64 NuttX compile only; no device backend, application registration or hardware execution')
(O/'native-result.json').write_text(json.dumps(report,indent=2)+'\n')
print('TOOL_NATIVE_COMPILE',p.returncode);print(p.stdout.decode(errors='replace')[-3000:])
