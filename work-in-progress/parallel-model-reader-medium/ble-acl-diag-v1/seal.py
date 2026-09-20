from pathlib import Path
import hashlib,json
p=Path(__file__).parent
h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
items=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(items,indent=2))
(p/'delivery.json').write_text(json.dumps({'status':'HOST_TESTED_CANDIDATE','outputs_sha256':h(p/'outputs.json'),'patch_sha256':h(p/'candidate.patch'),'inputs_sha256':h(p/'inputs.json')},indent=2))
for n in ['delivery.json','outputs.json','candidate.patch','inputs.json']:print(n,h(p/n))
