import hashlib
import json
from pathlib import Path
H=Path(__file__).resolve().parent
outputs={p.relative_to(H).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(H.rglob('*')) if p.is_file() and p.name not in ('outputs.json','delivery.json')}
(H/'outputs.json').write_text(json.dumps(outputs,indent=2))
d=dict(status='CANDIDATE_HOST_CHECKED_NOT_CONFIGURED',outputs_sha256=hashlib.sha256((H/'outputs.json').read_bytes()).hexdigest())
(H/'delivery.json').write_text(json.dumps(d,indent=2))
print(json.dumps(d))
print('delivery_sha256='+hashlib.sha256((H/'delivery.json').read_bytes()).hexdigest())
