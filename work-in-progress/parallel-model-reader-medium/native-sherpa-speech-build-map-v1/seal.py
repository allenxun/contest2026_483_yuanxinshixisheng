from pathlib import Path
import json,hashlib
p=Path(__file__).parent
outs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'SHERPA_STATIC_BUILD_MAP_NOT_CONFIGURED_OR_RUN','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest()};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())

