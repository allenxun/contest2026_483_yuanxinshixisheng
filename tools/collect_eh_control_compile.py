"""Capture exact target compile command and preprocessor macros, read-only."""
import json, subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/build/eh-control-20260910'
script=r'''
import hashlib,json,shlex,subprocess
from pathlib import Path
B=Path('/home/swl/openvela/cmake_out/velavision_eh_control_20260910')
db=json.loads((B/'compile_commands.json').read_text())
u=next(x for x in db if x['file'].endswith('/k7ehcontrol_main.cxx'))
args=shlex.split(u['command']);cmd=[];i=0
while i<len(args):
 a=args[i];i+=1
 if a in ['-o','-MF','-MT','-MQ']:i+=1;continue
 if a in ['-MD','-MMD','-c']:continue
 cmd.append(a)
p=subprocess.run(cmd+['-dM','-E'],cwd=u['directory'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=60)
print(json.dumps(dict(unit=u,preprocess_command=cmd+['-dM','-E'],exit_code=p.returncode,macros=p.stdout,stderr=p.stderr,source_sha256=hashlib.sha256(Path(u['file']).read_bytes()).hexdigest(),elf_sha256=hashlib.sha256((B/'nuttx').read_bytes()).hexdigest())))
'''
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*opts,'swl@192.168.152.131','python3 -'],input=script,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
assert p.returncode==0,p.stderr
r=json.loads(p.stdout)
with (E/'control-compile.json').open('x',encoding='utf-8') as f:json.dump(r,f,indent=2)
assert r['exit_code']==0
print('Captured exact command and target macros')
