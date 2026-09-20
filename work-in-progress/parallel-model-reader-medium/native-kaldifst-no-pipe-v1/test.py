import hashlib,json,subprocess
from pathlib import Path
H=Path(__file__).resolve().parent
D=H.parent/'native-sherpa-offline-stage-v3/sources'
K=D/'kaldifst/kaldifst/csrc'
src=[K/(x+'.cc') for x in ('kaldi-table','parse-options','text-utils')]
records=[]
for opt in ('O0','O2'):
 cmd=['D:/software/mingw64/mingw64/bin/g++.exe','-std=c++17','-'+opt,'-D__NuttX__','-I'+str(D/'kaldifst'),'-I'+str(D/'openfst/src/include'),str(H/'kaldi-io.cc'),str(H/'test.cc'),*[str(x) for x in src],'-o',str(H/(opt+'.exe'))]
 q=subprocess.run(cmd,capture_output=True,timeout=60);(H/(opt+'-build.log')).write_bytes(q.stdout+q.stderr)
 records.append(dict(command=cmd,exit_code=q.returncode));assert q.returncode==0,q.stderr.decode()
 q=subprocess.run([str(H/(opt+'.exe'))],cwd=H,capture_output=True,timeout=10);(H/(opt+'-run.log')).write_bytes(q.stdout+q.stderr)
 records.append(dict(command=[str(H/(opt+'.exe'))],exit_code=q.returncode));assert q.returncode==0
(H/'test-results.json').write_text(json.dumps(records,indent=2))
(H/'test-inputs.json').write_text(json.dumps({str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in src},indent=2))
print('O0/O2 real-source tests passed')
