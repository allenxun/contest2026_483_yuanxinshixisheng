"""Capture exact target disassembly and libc++abi source after the failed probe."""
import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/cxx-eh-20260910/diagnostics';E.mkdir(exist_ok=True)
script=r'''
import hashlib,json,shlex,subprocess
from pathlib import Path
B=Path('/home/swl/openvela/cmake_out/velavision_cxx_eh_20260910');elf=B/'nuttx'
prefix='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-'
out={}
def run(name,cmd,cwd=None):
 p=subprocess.run(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 out[name]=dict(command=cmd,exit_code=p.returncode,text=p.stdout)
for symbol in ['_Unwind_RaiseException_Phase2','_Unwind_RaiseException','_Unwind_Find_FDE','__cxa_get_globals','__cxa_get_globals_fast']:
 run(symbol,[prefix+'objdump','-d','--disassemble='+symbol,str(elf)])
run('probe-disassembly',[prefix+'objdump','-d','--start-address=0x40455cd4','--stop-address=0x404560b0',str(elf)])
run('lsda',[prefix+'objdump','-s','-j','.gcc_except_table',str(elf)])
source=Path('/home/swl/openvela/nuttx/libs/libxx/libcxxabi/libcxxabi/src/cxa_exception_storage.cpp')
out['cxa_exception_storage.cpp']=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),text=source.read_text())
db=json.loads((B/'compile_commands.json').read_text());u=next(x for x in db if x['file'].endswith('/cxa_exception_storage.cpp'))
argv=shlex.split(u['command']);cmd=[];i=0
while i<len(argv):
 a=argv[i];i+=1
 if a in ['-o','-MF','-MT','-MQ']:i+=1;continue
 if a in ['-MD','-MMD','-c']:continue
 cmd.append(a)
run('abi-macros',cmd+['-dM','-E'],u['directory'])
run('gcc-unwind-source-search',['find','/home/swl/openvela/prebuilts/gcc','-name','unwind.inc'])
print(json.dumps(out))
'''
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*opts,'swl@192.168.152.131','python3 -'],input=script,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
assert p.returncode==0,p.stderr
result=json.loads(p.stdout)
for name,item in result.items():
    with (E/(name+'.txt')).open('x',encoding='utf-8') as f:f.write(item['text'])
with (E/'index.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print('Captured',len(result),'exact source/disassembly records')
