from pathlib import Path
import json,hashlib
p=Path(__file__).parent;root=p.parents[2];inp=root/'evidence/native-strptime-input-20260911'
files=list(inp.iterdir())+[root/'private/native-ort-env-stage/abseil_cpp/absl/time/internal/cctz/src/time_zone_format.cc',root/'evidence/native-static-deps2-20260911/build.log']
inputs={str(f):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in files if f.is_file()};(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
outputs={f.name:{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(p.iterdir()) if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outputs,indent=2));d={'status':'CONFIG_AND_BUILD_REVIEW_TARGET_REBUILD_LINK_RUN_PENDING','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest()};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print('delivery_sha256='+hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
