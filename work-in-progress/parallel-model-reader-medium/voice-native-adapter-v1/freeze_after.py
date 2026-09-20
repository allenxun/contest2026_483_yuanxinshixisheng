from pathlib import Path
import json,hashlib
r=Path('E:/openvela/VelaVision');p=Path(__file__).parent;a=[]
for x in json.loads((p/'before-inputs.json').read_text()):
 f=r/x['path'];b=f.read_bytes();q=p/'after'/x['path'];q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b);a.append({'path':x['path'],'sha256':hashlib.sha256(b).hexdigest()})
(p/'after-inputs.json').write_text(json.dumps(a,indent=2))
print('after frozen',len(a))
