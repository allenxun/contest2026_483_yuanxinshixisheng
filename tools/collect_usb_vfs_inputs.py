"""Snapshot selected real SDK USB mass-storage/FAT sources, read-only."""
import base64,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/usb-storage-vfs-20260910';E.mkdir(exist_ok=True)
script=r'''
import base64,hashlib,json
from pathlib import Path
N=Path('/home/swl/openvela/nuttx')
paths=[N/'fs/vfs/fs_mount.c',N/'fs/vfs/fs_open.c',N/'include/fcntl.h',N/'fs/vfs/fs_write.c',N/'fs/vfs/fs_umount.c']
out=[]
for p in paths:
 if not p.is_file():out.append(dict(path=str(p.relative_to(N)),missing=True));continue
 data=p.read_bytes();out.append(dict(path=str(p.relative_to(N)),sha256=hashlib.sha256(data).hexdigest(),base64=base64.b64encode(data).decode()))
print(json.dumps(out))
'''
opts=['-i',r'C:\Users\pc2025\Documents\Codex\2026-09-03\new-chat\work\ssh\ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
p=subprocess.run(['ssh.exe',*opts,'swl@192.168.152.131','python3 -'],input=script,text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
assert p.returncode==0,p.stderr
rows=json.loads(p.stdout)
for x in rows:
 if x.get('missing'):continue
 data=base64.b64decode(x.pop('base64'));assert hashlib.sha256(data).hexdigest()==x['sha256']
 out=E/'nuttx'/x['path'];out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('xb') as f:f.write(data)
 x['bytes']=len(data)
with (E/'inputs.json').open('x',encoding='utf-8') as f:json.dump(rows,f,indent=2)
print('Captured selected SDK sources:',len(rows),'missing:',[x['path'] for x in rows if x.get('missing')])
