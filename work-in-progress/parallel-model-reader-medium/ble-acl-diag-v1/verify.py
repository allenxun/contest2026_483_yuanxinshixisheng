from pathlib import Path
import hashlib,json
p=Path(__file__).parent
items=json.loads((p/'outputs.json').read_text())
for v in items:assert hashlib.sha256((p/v['path']).read_bytes()).hexdigest()==v['sha256'],v['path']
print('Verified',len(items),'files')
