from pathlib import Path
import json,hashlib
p=Path(__file__).parent
v1=p.parent/'native-sherpa-deps-v1';(p/'prior-inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [v1/'delivery.json',v1/'download-results.json',v1/'nested-download-results.json']},indent=2))
outs={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.rglob('*') if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'FIVE_ADDITIONAL_OFFICIAL_ARCHIVES_VERIFIED_ASR_INPUTS_NOT_BUILT','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest()};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
