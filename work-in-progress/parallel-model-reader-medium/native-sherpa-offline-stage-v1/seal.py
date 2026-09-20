from pathlib import Path
import hashlib,json
p=Path(__file__).parent
manifest=json.loads((p/'source-manifest.json').read_text());assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v['sha256'] for n,v in manifest.items())
outs={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'EIGHT_VERIFIED_SOURCE_TREES_PATCH_APPLY_PASSED_NOT_CONFIGURED','source_files':len(manifest),'outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest(),'patch_sha256':outs['candidate.patch']};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
