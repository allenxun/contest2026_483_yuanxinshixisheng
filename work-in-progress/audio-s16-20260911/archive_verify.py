import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
revision = 'audio-s16-20260911'
evidence = root / 'evidence/build' / revision
artifacts = root / 'artifacts' / revision

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert sha256(artifacts / 'nuttx.bin') == '34972feb5a1b5f16c73efdeeec7c8ef2dc39a204dcaafec8d6027ed17cca270e'

source_paths = [
    path for path in Path(__file__).resolve().parent.iterdir()
    if path.suffix in ('.cpp', '.cc', '.hpp', '.h', '.c')
]
source_paths += [
    path for path in (root / 'app/k7sound').iterdir()
    if path.suffix in ('.c', '.h')
]
sources = {
    str(path.relative_to(root)).replace('\\', '/'): sha256(path)
    for path in source_paths
}

report = {
    'build_exit_code': 0,
    'sources': sources,
    'artifacts': {
        name: {'bytes': (artifacts / name).stat().st_size,
               'sha256': sha256(artifacts / name)}
        for name in ('nuttx', 'nuttx.bin', '.config')
    },
    'hardware_tested': False,
}
(evidence / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')

sys.path.insert(0, str(root / 'tools'))
import verify_voice_memset_image as verify
import audit_arm64_unwind as arm64

verify.REV = revision
verify.audit = arm64.audit
result = verify.verify(artifacts)
(evidence / 'image-audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items() if key != 'unwind'}))
