from pathlib import Path
import json,hashlib
p=Path(__file__).parent
files={str(f.relative_to(p)):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(p.rglob('*')) if f.is_file() and f.name not in ('outputs.json','delivery.json')}
(p/'outputs.json').write_text(json.dumps(files,indent=2));d={'status':'SOURCE_CANDIDATE_TARGET_COMPILE_PENDING','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest(),'candidate_sha256':files['elf_mem_image.h']['sha256'],'patch_sha256':files['candidate.patch']['sha256']};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(json.dumps(d));print('delivery_sha256='+hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())

