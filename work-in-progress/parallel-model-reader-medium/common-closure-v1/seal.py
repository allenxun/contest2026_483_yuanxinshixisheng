from pathlib import Path
import hashlib,json
p=Path(__file__).parent
files={str(f.relative_to(p)):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(p.iterdir()) if f.is_file() and f.name not in ('outputs.json','delivery.json')}
(p/'outputs.json').write_text(json.dumps(files,indent=2))
d={'status':'READ_ONLY_COMMON_SOURCE_AND_DECLARED_DEPENDENCY_AUDIT_NOT_NATIVE_LINK','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest(),'common_units':21,'abseil_declared_targets':97,'target_terminate_reclamation_proven':False}
(p/'delivery.json').write_text(json.dumps(d,indent=2));print(json.dumps(d));print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
