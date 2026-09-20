from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
target=r/'apps/examples/k7host/k7_preview.c';plan=json.loads((w/'install-plan.json').read_text())
item=next(i for i in plan if i['target']=='apps/examples/k7host/k7_preview.c')
assert sha(target)==item['new_sha256']
paced=w/'k7_preview.paced.c';assert paced.exists()
backup=w/'k7_preview.c.v23-unpaced';assert not backup.exists();backup.write_bytes(target.read_bytes())
target.write_bytes(paced.read_bytes());item['new_sha256']=sha(target);item['local']='k7_preview.paced.c'
(w/'install-plan.json').write_text(json.dumps(plan,indent=2))
print('Installed paced sub-64-byte preview records; preserved unpaced source')
