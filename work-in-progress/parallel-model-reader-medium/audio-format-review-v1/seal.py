from pathlib import Path
import hashlib,json
p=Path(__file__).parent; h=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
a=[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':h(f)} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ['outputs.json','delivery.json']]
(p/'outputs.json').write_text(json.dumps(a,indent=2));(p/'delivery.json').write_text(json.dumps({'status':'READ_ONLY_FORMAT_REVIEW','outputs_sha256':h(p/'outputs.json'),'inputs_sha256':h(p/'inputs.json')},indent=2))
for x in a:assert h(p/x['path'])==x['sha256']
for n in ['delivery.json','outputs.json','inputs.json']:print(n,h(p/n))
print('Verified',len(a),'files')
