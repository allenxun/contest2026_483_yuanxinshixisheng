from pathlib import Path
import json,hashlib,re
p=Path(__file__).parent;rows=[]
for f in (p/'cmake-snapshots').rglob('*.cmake'):
 t=f.read_text(encoding='utf-8');ls=[{'line':i,'text':l.strip()} for i,l in enumerate(t.splitlines(),1) if re.search(r'set\(.*(URL|HASH)|FetchContent_Declare',l)]
 if ls:rows.append({'source':str(f.relative_to(p)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'settings':ls})
(p/'recursive-recipes.json').write_text(json.dumps(rows,indent=2))
outs={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'THREE_OFFICIAL_ARCHIVES_VERIFIED_NESTED_LOCKS_INSPECTED_NOT_BUILT','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest()};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
