from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
for r in json.loads((p/'inputs.json').read_text()):assert hashlib.sha256((p/r['snapshot']).read_bytes()).hexdigest()==r['sha256'],r['snapshot']
rows=json.loads((p/'outputs.json').read_text())
for r in rows:assert hashlib.sha256((p/r['path']).read_bytes()).hexdigest()==r['sha256'],r['path']
print('verified',len(rows),'files; backend inputs unchanged')
