from pathlib import Path
import json,hashlib
p=Path(__file__).resolve().parent
for r in json.loads((p/'inputs.json').read_text()):
 assert hashlib.sha256((p/r['snapshot']).read_bytes()).hexdigest()==r['sha256'],r['snapshot']
rows=json.loads((p/'outputs.json').read_text())
for r in rows:
 f=p/r['path'];assert f.stat().st_size==r['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==r['sha256'],r['path']
print('verified',len(rows),'files and all frozen inputs')
