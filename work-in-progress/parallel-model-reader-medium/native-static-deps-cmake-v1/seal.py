from pathlib import Path
import json,hashlib
p=Path(__file__).parent
files={f.name:{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(p.iterdir()) if f.is_file() and f.name not in ('outputs.json','delivery.json')}
(p/'outputs.json').write_text(json.dumps(files,indent=2));d={'status':'CMAKE_CANDIDATE_NATIVE_CONFIGURE_BUILD_PENDING','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest(),'cmake_sha256':files['CMakeLists.txt']['sha256'],'abseil_root_targets':21};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(json.dumps(d));print('delivery_sha256='+hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
