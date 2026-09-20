"""Compile staged Agent parser with real NuttX C++ flags, without firmware edits."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'private/tool-json-native-20260910';S.mkdir(exist_ok=True)
E=R/'evidence/agent-tool-json-20260910';assert not (E/'native-result.json').exists()
source=R/'app/k7agent/tool_api'
files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.suffix in {'.cpp','.hpp'}}
(S/'inputs.json').write_text(json.dumps(files))
remote=r'''
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
'''
(S/'run.py').write_text(remote,encoding='utf-8',newline='\n')
with tarfile.open(S/'stage.tar.gz','w:gz') as t:
    for name in files:t.add(source/name,arcname=name)
    for name in ['inputs.json','run.py']:t.add(S/name,arcname=name)
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/tool-json-native-20260910'
def run(cmd):subprocess.run(cmd,check=True,timeout=90)
run(['ssh.exe',*opts,host,'mkdir '+dest])
run(['scp.exe',*opts,str(S/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'])
run(['ssh.exe',*opts,host,'tar -xzf '+dest+'/stage.tar.gz -C '+dest+' && python3 '+dest+'/run.py'])
run(['scp.exe',*opts,'-r',host+':'+dest+'/result/.',str(E)])
(E/'native-inputs.json').write_bytes((S/'inputs.json').read_bytes())
(E/'native-runner.py').write_bytes((S/'run.py').read_bytes())
