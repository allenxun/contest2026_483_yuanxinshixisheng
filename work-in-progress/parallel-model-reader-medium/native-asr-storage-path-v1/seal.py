import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[2]
names=['app/k7storage/k7storage_main.c','app/k7storage/README.md','app/k7fat/k7fat_main.c','app/k7fat/Kconfig','app/k7fat/README.md','app/k7agent/model_reader/model_reader.c','app/k7agent/model_reader/model_reader.h','port/tracked/nuttx/fs/fat/Kconfig','docs/USB只读模型存储接入_20260910.md','evidence/usb-readonly-20260910/runtime-acceptance.json','evidence/usb-readonly-20260910/read.bin','evidence/build/fat-readonly-20260910/verification.json','work-in-progress/parallel-model-reader-medium/fat-reader-contract-v1/HANDOFF.md','work-in-progress/parallel-neon-probe-medium/model-file-integration-v1/HANDOFF.md','evidence/native-speech-ort-conversion1-20260911/encoder.json','evidence/native-speech-ort-conversion1-20260911/decoder.json']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(H/'inputs.json').write_text(json.dumps({n:sha(R/n) for n in names},indent=2))
(H/'outputs.json').write_text(json.dumps({p.name:sha(p) for p in H.iterdir() if p.is_file() and p.name not in ('outputs.json','delivery.json')},indent=2))
(H/'delivery.json').write_text(json.dumps(dict(status='READ_ONLY_PLAN_NO_DEVICE_ACTION',outputs_sha256=sha(H/'outputs.json')),indent=2))
print('delivery',sha(H/'delivery.json'));print('outputs',sha(H/'outputs.json'))
