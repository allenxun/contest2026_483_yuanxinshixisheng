"""Verify independent delivery indexes without rewriting their evidence."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
out=R/'evidence/agent-prerequisites-20260910/delivery-review.json'
assert not out.exists()
results=[]
for name in ['parallel-cxx-unwind-medium','parallel-model-reader-medium','parallel-llama-pool-safety']:
    root=R/'work-in-progress'/name
    raw=(root/'delivery.json').read_bytes();index=json.loads(raw)
    bad=[]
    for item in index['files']:
        p=(root/item['path']).resolve();assert p.is_relative_to(root)
        data=p.read_bytes()
        if hashlib.sha256(data).hexdigest()!=item['sha256'] or ('bytes' in item and len(data)!=item['bytes']):bad.append(item['path'])
    results.append(dict(delivery=name,files=len(index['files']),mismatches=bad,index_sha256=hashlib.sha256(raw).hexdigest()))
name='parallel-neon-probe-medium';root=R/'work-in-progress'/name
raw=(root/'hashes.json').read_bytes();index=json.loads(raw)
bad=[path for path,digest in index['outputs'].items() if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest]
results.append(dict(delivery=name,files=len(index['outputs']),mismatches=bad,index_sha256=hashlib.sha256(raw).hexdigest()))
out.write_text(json.dumps(dict(results=results,scope='Current output hash checks, not independent repetition of host tests or board acceptance'),indent=2)+'\n')
print(json.dumps(results))
assert not any(r['mismatches'] for r in results)
