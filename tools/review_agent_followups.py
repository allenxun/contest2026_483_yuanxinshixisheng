"""Hash-check the three newly delivered isolated candidates."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];results=[]
for rel,index_name in [('parallel-cxx-unwind-medium/concurrent-probe-v1','delivery.json'),
                       ('parallel-model-reader-medium/integrity-v1','delivery.json'),
                       ('parallel-neon-probe-medium/affinity-v1','hashes.json')]:
    root=R/'work-in-progress'/rel;raw=(root/index_name).read_bytes();index=json.loads(raw)
    items=index.get('files') or [dict(path=p,sha256=h) for p,h in index['outputs'].items()]
    for item in items:
        p=(root/item['path']).resolve();assert p.is_relative_to(root)
        data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256'],p
        assert 'bytes' not in item or len(data)==item['bytes']
    results.append(dict(candidate=rel,files=len(items),index_sha256=hashlib.sha256(raw).hexdigest()))
out=R/'evidence/agent-prerequisites-20260910/followup-delivery-review.json'
with out.open('x',encoding='utf-8') as f:json.dump(dict(deliveries=results,scope='Output integrity only; no integration/target acceptance'),f,indent=2)
print(json.dumps(results))
