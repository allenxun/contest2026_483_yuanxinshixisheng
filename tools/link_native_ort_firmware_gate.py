"""Final ELF link with actual SDK objects; no board loading or SDK mutation."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-ort-firmware-link1';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-firmware-link1-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,re,shlex,struct,subprocess,tarfile
from pathlib import Path
B=Path('/dev/shm/velavision_audio_sound_20260910')
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'firmware-link1';O.mkdir()
gate=json.loads((S/'link-attempt2/result.json').read_text());assert gate['missing_count']==0
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
runtime=S/'link-attempt2/session.o';assert sha(runtime)==gate['relocatable_sha256']
original=sha(B/'nuttx')
lines=(B/'build.ninja').read_text().splitlines()
i=next(i for i,x in enumerate(lines) if x.startswith('build nuttx: '))
objects=shlex.split(lines[i].split(' ',3)[3].split(' |')[0])
values={}
for line in lines[i+1:]:
 if not line.startswith('  '):break
 key,value=line.strip().split(' = ',1);values[key]=value
compiler='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-g++'
flags=shlex.split(values['LINK_FLAGS'].replace('-Map=nuttx.map','-Map='+str(O/'nuttx.map')))
libs=shlex.split(values['LINK_LIBRARIES'])
cmd=[compiler,*objects,str(runtime),*flags,'-Wl,--undefined=k7_ort_add_probe','-o',str(O/'nuttx'),*libs]
q=subprocess.run(cmd,cwd=B,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
(O/'link.log').write_bytes(q.stdout)
result=dict(exit_code=q.returncode,command=cmd,base_firmware_sha256=original,runtime_sha256=sha(runtime),
 inputs=[dict(path=str(B/x) if not Path(x).is_absolute() else x,sha256=sha(B/x)) for x in objects+[x for x in libs if x.endswith('.a')]],
 board_loaded=False,model_run=False,command_registered=False)
assert sha(B/'nuttx')==original
if q.returncode==0:
 data=(O/'nuttx').read_bytes();phoff=struct.unpack_from('<Q',data,32)[0];step,count=struct.unpack_from('<HH',data,54)
 loads=[]
 for j in range(count):
  h=struct.unpack_from('<IIQQQQQQ',data,phoff+j*step)
  if h[0]==1:loads.append(dict(start=hex(h[4]),end=hex(h[4]+h[6]),file_bytes=h[5],memory_bytes=h[6]))
 result.update(elf_sha256=sha(O/'nuttx'),loads=loads,memory_end=hex(max(int(x['end'],16) for x in loads)))
 tool=str(Path(compiler).with_name('aarch64-none-elf-nm'))
 (O/'undefined.txt').write_text(subprocess.check_output([tool,'-u',str(O/'nuttx')],text=True))
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for x in O.iterdir():
  if x.suffix in ('.json','.log','.txt'):t.add(x,arcname=x.name)
print(json.dumps({k:v for k,v in result.items() if k not in ('command','inputs')}),flush=True)
print(q.stdout.decode(errors='replace')[-4000:],flush=True)
'''
(P/'link.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
subprocess.run(['scp.exe',*options,str(P/'link.py'),host+':'+dest+'/link-firmware.py'],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/link-firmware.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/firmware-link1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
