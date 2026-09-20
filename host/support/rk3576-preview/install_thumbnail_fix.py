from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((w/'install-plan.json').read_text())
updates=[('apps/examples/k7host/k7_preview.c','k7_preview.thumbnail.c'),
         ('apps/examples/k7host/k7_pipeline.c','k7_pipeline.thumbnail.c')]
for target,local in updates:
 item=next(i for i in plan if i['target']==target);p=r/target
 assert sha(p)==item['new_sha256'],target
 source=w/local;assert source.exists(),local
 backup=w/(Path(target).name+'.v23-fulljpeg');assert not backup.exists();backup.write_bytes(p.read_bytes())
 p.write_bytes(source.read_bytes());item['new_sha256']=sha(p);item['local']=local
(w/'install-plan.json').write_text(json.dumps(plan,indent=2))
print('Installed RGB160 thumbnail encoder and pipeline input; preserved full-JPEG sources')
