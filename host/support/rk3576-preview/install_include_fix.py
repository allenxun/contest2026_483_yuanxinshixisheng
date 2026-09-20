from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((w/'install-plan.json').read_text());item=next(i for i in plan if i['target']=='apps/examples/k7host/k7_preview.c')
p=r/item['target'];assert sha(p)==item['new_sha256']
fixed=w/'k7_preview.final.c';assert fixed.exists();backup=w/'k7_preview.c.v23-include-order';assert not backup.exists();backup.write_bytes(p.read_bytes())
p.write_bytes(fixed.read_bytes());item['new_sha256']=sha(p);item['local']='k7_preview.final.c'
(w/'install-plan.json').write_text(json.dumps(plan,indent=2));print('Installed stdio-before-jpeglib include fix')
