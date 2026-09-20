import hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[2]
names=['evidence/resource-audit-20260910/live-uboot.json','evidence/resource-audit-20260910/emmc-observation.json','evidence/usb-readonly-20260910/runtime-acceptance.json','evidence/usb-readonly-20260910/read.bin','docs/USB只读模型存储接入_20260910.md']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(H/'inputs.json').write_text(json.dumps({n:sha(R/n) for n in names},indent=2))
(H/'outputs.json').write_text(json.dumps({p.name:sha(p) for p in H.iterdir() if p.is_file() and p.name not in ('outputs.json','delivery.json')},indent=2))
(H/'delivery.json').write_text(json.dumps(dict(status='READ_ONLY_UMS_CAPABILITY_NOT_PROVEN',outputs_sha256=sha(H/'outputs.json')),indent=2))
print('delivery',sha(H/'delivery.json'));print('outputs',sha(H/'outputs.json'))
