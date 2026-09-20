import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
manifest=root/'manifests/package_files.json'
data=json.loads(manifest.read_text(encoding='utf-8'))
failed=[]
for entry in data['files']:
    path=(root/entry['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():failed.append(entry['path']);continue
    if path.stat().st_size!=entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:failed.append(entry['path'])
print(json.dumps({'verified_files':len(data['files']),'failures':failed},ensure_ascii=False))
sys.exit(bool(failed))
