"""Verify immutable agent output manifests; no candidate execution or integration."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
targets=[
 'parallel-model-reader-medium/model-arena-plan-v1',
 'parallel-model-reader-medium/model-arena-buft-v1',
 'parallel-neon-probe-medium/amsdu-audit-v1/diagnostic-candidate',
 'parallel-cxx-unwind-medium/eh-control-elf-review-v1']
out=[]
for rel in targets:
 d=R/'work-in-progress'/rel
 p=d/'delivery.json'
 if not p.exists():
  out.append(dict(path=rel,manifest=None,verified=False,reason='No delivery.json; inspect alternate index manually'))
  continue
 m=json.loads(p.read_text(encoding='utf-8'));rows=m.get('files',[])
 if not isinstance(rows,list):
  out.append(dict(path=rel,verified=False,reason='Alternate manifest schema needs explicit review'));continue
 checked=[]
 for row in rows:
  n=row.get('path',row.get('file'))
  assert n is not None,row
  f=(d/n).resolve();assert f.is_relative_to(d.resolve())
  data=f.read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256'],str(f)
  if 'bytes' in row:assert len(data)==row['bytes']
  checked.append(n)
 out.append(dict(path=rel,manifest_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),verified=bool(checked),files=checked))
e=R/'evidence/agent-increment-20260910';e.mkdir(exist_ok=True)
with (e/'review.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
print(json.dumps([dict(path=x['path'],verified=x['verified'],count=len(x.get('files',[]))) for x in out]))
