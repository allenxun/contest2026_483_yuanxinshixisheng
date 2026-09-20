"""Build a review patch only when the supplied passing test evidence matches."""
import argparse
import datetime
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('report', help='Passing run result.json within this directory')
args = parser.parse_args()
report_path = (root / args.report).resolve()
report_path.relative_to(root)
report = json.loads(report_path.read_text(encoding='utf-8'))
if not report['passed'] or not report.get('sources_unchanged_during_run'):
    raise SystemExit('Refusing delivery: tests failed or sources changed during run')
for name, digest in report['candidate_sha256'].items():
    p = root / name
    if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        raise SystemExit('Refusing delivery: changed tested file ' + name)
lock = json.loads((root/'vendor/sherpa-onnx/version-lock.json').read_text(encoding='utf-8'))
for name, digest in lock['files'].items():
    if hashlib.sha256((root/'vendor/sherpa-onnx'/name).read_bytes()).hexdigest() != digest:
        raise SystemExit('Dependency checksum mismatch: ' + name)
changed = ['include/voicelink/types.hpp', 'include/voicelink/ports.hpp',
           'include/voicelink/controller.hpp', 'src/core.cpp']
added = ['include/voicelink/audio.hpp', 'src/audio.cpp',
         'tests/test_async.cpp', 'tests/test_audio.cpp']
patch = []
for name in changed + added:
    old = (root/'input'/name).read_text(encoding='utf-8-sig').splitlines(True) if name in changed else []
    new = (root/name).read_text(encoding='utf-8').splitlines(True)
    patch.extend(difflib.unified_diff(old, new, fromfile='a/'+name if old else '/dev/null', tofile='b/'+name))
(root/'candidate.patch').write_text(''.join(patch), encoding='utf-8')
files = changed + added + ['src/parsers.cpp', 'include/voicelink/parsers.hpp',
    'run_tests.py', 'prepare_candidate.py', 'package_delivery.py', 'candidate.patch',
    'HANDOFF.md', '接口与审查.md', 'vendor/sherpa-onnx/version-lock.json']
manifest = {'session_id': report['session_id'], 'tests': report_path.relative_to(root).as_posix(),
            'tested_files_unchanged': True,
            'original_input_unchanged': all(c['unchanged'] for c in report['input_checks']),
            'files': {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}}
content = json.dumps(manifest, ensure_ascii=False, indent=2)
stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
(root/'evidence'/('delivery-'+stamp+'.json')).write_text(content, encoding='utf-8')
(root/'evidence/delivery.json').write_text(content, encoding='utf-8')
print('Delivery verified; patch lines=' + str(len(patch)))
