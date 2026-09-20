"""Read current SDK MMU sources over SSH and freeze local review inputs."""
import base64
import hashlib
import importlib.util
import json
import shlex
import subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
O=R/'evidence/audio-mmu-input-20260911'
O.mkdir(exist_ok=False)
script='''from pathlib import Path
import json,base64
r=Path('/home/swl/openvela/nuttx/arch/arm64')
names={'arm64_mmu.c','arm64_mmu.h','arm64_arch.h'}
rows=[]
for p in sorted(r.rglob('*')):
 if p.name in names and p.is_file():rows.append({'path':str(p),'data':base64.b64encode(p.read_bytes()).decode()})
print(json.dumps(rows))
'''
options=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519',
 '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8',
 '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*options,'swl@192.168.152.131','python3 -c '+shlex.quote(script)],capture_output=True,timeout=30)
(O/'ssh-stderr.txt').write_bytes(p.stderr)
assert p.returncode==0
rows=[]
for row in json.loads(p.stdout):
 data=base64.b64decode(row['data']); name=Path(row['path']).name
 target=O/name;assert not target.exists();target.write_bytes(data)
 rows.append(dict(source=row['path'],file=name,sha256=hashlib.sha256(data).hexdigest()))
assert {r['file'] for r in rows}=={'arm64_mmu.c','arm64_mmu.h','arm64_arch.h'}
spec=importlib.util.spec_from_file_location('layout',R/'work-in-progress/parallel-cxx-unwind-medium/llama-layout-v1/audit_layout.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
elf=mod.parse(R/'artifacts/audio-mmu-20260910/nuttx')
(O/'elf-table-symbols.json').write_text(json.dumps(dict(sha256=elf['sha256'],symbols={k:hex(v) for k,v in elf['symbols'].items() if any(x in k for x in ('xlat_table','_sbss','_ebss'))}),indent=2))
for rel,name in [('artifacts/audio-mmu-20260910/.config','config'),('port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c','rk3576_boot.c')]:
 data=(R/rel).read_bytes();(O/name).write_bytes(data)
 rows.append(dict(source=rel,file=name,sha256=hashlib.sha256(data).hexdigest()))
(O/'inputs.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows))
