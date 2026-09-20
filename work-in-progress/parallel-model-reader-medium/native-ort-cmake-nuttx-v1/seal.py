from pathlib import Path
import json,hashlib
p=Path(__file__).parent
outs={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'MINIMAL_CMAKE_SOURCE_CANDIDATE_NOT_TARGET_CONFIGURED','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest(),'patch_sha256':outs['candidate.patch']};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
