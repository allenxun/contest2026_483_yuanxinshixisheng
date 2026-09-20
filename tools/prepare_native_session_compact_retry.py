"""Preserve runtime sections while removing debug-only intermediate data."""
import subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'private/native-ort-compact';P.mkdir(exist_ok=True)
O=R/'evidence/native-ort-compact-20260911';O.mkdir(exist_ok=True)
remote=r'''
import hashlib,json,os,struct,subprocess,tarfile
from pathlib import Path
S=Path('/dev/shm/velavision-ort-session-20260911');O=S/'compact-attempt1';O.mkdir()
assert json.loads((S/'compile-attempt4/result.json').read_text())['exit_code']==1
running=subprocess.run(['pgrep','-x','ninja'],stdout=subprocess.PIPE)
assert running.returncode==1,'build must be stopped before intermediate changes'
source=S/'ort/onnxruntime/core/optimizer/selectors_actions/selector_action_transformer.cc'
before=source.read_bytes();text=before.decode()
old='for (const auto op_schema : action_saved_state.produced_node_op_schemas)'
assert text.count(old)==1
source.write_text(text.replace(old,'for (const auto& op_schema : action_saved_state.produced_node_op_schemas)'))
(O/'selector.before.cc').write_bytes(before)
(O/'selector.after.cc').write_bytes(source.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def alloc_sections(b):
 assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
 offset=struct.unpack_from('<Q',b,40)[0]
 step,count,names=struct.unpack_from('<HHH',b,58)
 assert step==64 and count>0 and names<count
 headers=[struct.unpack_from('<IIQQQQIIQQ',b,offset+i*step) for i in range(count)]
 h=headers[names];strings=b[h[4]:h[4]+h[5]]
 result=[]
 for h in headers:
  if h[2]&2:
   name=strings[h[0]:].split(b'\0',1)[0].decode()
   raw=b'' if h[1]==8 else b[h[4]:h[4]+h[5]]
   result.append((name,h[1],h[2],h[5],h[8],sha(raw)))
 return result
objcopy='/home/swl/openvela/prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-objcopy'
results=[]
for p in sorted((S/'build').rglob('*')):
 if p.suffix not in ('.o','.obj') or not p.is_file():continue
 b=p.read_bytes()
 if b[:4]!=b'\x7fELF':continue
 st=p.stat();sections=alloc_sections(b)
 tmp=p.with_name(p.name+'.compact')
 q=subprocess.run([objcopy,'--strip-debug',str(p),str(tmp)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
 assert q.returncode==0,q.stdout
 after=tmp.read_bytes()
 assert alloc_sections(after)==sections,str(p)
 row=dict(path=str(p),before_sha256=sha(b),after_sha256=sha(after),before_bytes=len(b),after_bytes=len(after),alloc_sections_unchanged=True)
 os.replace(tmp,p);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
 results.append(row)
 (O/'objects.json').write_text(json.dumps(results,indent=2))
result=dict(objects=len(results),saved_bytes=sum(x['before_bytes']-x['after_bytes'] for x in results),
 allocated_sections_preserved=True,source_before_sha256=sha(before),source_after_sha256=sha(source.read_bytes()),
 note='Only generated target intermediate debug sections stripped; source, commands, diagnostics and unwind/runtime sections retained. Temporary remount denied by sudo password; no mount changed.')
(O/'result.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for p in O.iterdir():
  if p.suffix in ('.json','.cc'):t.add(p,arcname=p.name)
print(json.dumps(result),flush=True)
'''
(P/'prepare.py').write_text(remote)
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/dev/shm/velavision-ort-session-20260911'
subprocess.run(['scp.exe',*options,str(P/'prepare.py'),host+':'+dest+'/compact.py'],check=True)
subprocess.run(['ssh.exe',*options,host,'python3 '+dest+'/compact.py'],check=True)
subprocess.run(['scp.exe',*options,host+':'+dest+'/compact-attempt1/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and '/' not in x.name and '\\' not in x.name
 t.extractall(O,filter='data')
