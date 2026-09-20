from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
manifest=json.loads((p/'outputs.json').read_text())
for row in manifest:
 f=p/row['path']; assert f.stat().st_size==row['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'], row['path']
for row in json.loads((p/'inputs.json').read_text()):
 assert hashlib.sha256((p/row['snapshot']).read_bytes()).hexdigest()==row['sha256'],row['source']
print('verified',len(manifest),'delivered files and frozen source snapshots')
