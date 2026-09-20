"""Host-only build and evidence capture. No SDK/device/network operations."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--compiler', default='g++')
parser.add_argument('--input-source', help='Optional original input path for integration drift checking')
args = parser.parse_args()
compiler = shutil.which(args.compiler)
if not compiler:
    raise SystemExit('C++ compiler not found: ' + args.compiler)
stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
out = root / 'evidence' / ('run-' + stamp)
out.mkdir(parents=True)
env = os.environ.copy()
env['PATH'] = str(Path(compiler).parent) + os.pathsep + env.get('PATH', '')
records = []
def source_hashes():
    hashes = {}
    for folder in ['src', 'include', 'tests', 'vendor', 'input']:
        for p in sorted((root / folder).rglob('*')):
            if p.is_file():
                hashes[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes
before = source_hashes()
def run(cmd, label):
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=120)
        raw, code = proc.stdout, proc.returncode
    except subprocess.TimeoutExpired as exc:
        raw, code, timed_out = exc.output or b'', 124, True
    except OSError as exc:
        raw, code = str(exc).encode('utf-8'), 125
    (out / (label + '.raw')).write_bytes(raw)
    output = raw.decode('utf-8', errors='replace')
    (out / (label + '.txt')).write_text(output, encoding='utf-8')
    records.append({'label': label, 'command': cmd, 'exit_code': code,
                    'timed_out': timed_out,
                    'output': str(out / (label + '.txt'))})
    print(label + ': ' + str(code))
    if output:
        print(output)
    return code == 0

ok = run([compiler, '--version'], 'compiler')
flags = ['-std=c++17', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
         '-finput-charset=UTF-8', '-fexec-charset=UTF-8']
jobs = []
for test in sorted((root / 'input/tests').glob('test_*.cpp')):
    jobs.append(('baseline-' + test.stem, ['-Iinput/include', 'input/src/core.cpp',
                'input/src/parsers.cpp', str(test)]))
jobs += [('candidate-async', ['-Iinclude', 'src/core.cpp', 'src/parsers.cpp', 'tests/test_async.cpp']),
         ('candidate-audio', ['-Iinclude', '-Ivendor', 'src/audio.cpp', 'tests/test_audio.cpp']),
         ('candidate-parsers', ['-Iinclude', 'src/parsers.cpp', 'input/tests/test_parsers.cpp'])]
for name, sources in jobs:
    exe = str(out / (name + ('.exe' if os.name == 'nt' else '')))
    built = run([compiler] + flags + sources + ['-o', exe], name + '-build')
    ok = built and ok
    if built:
        ok = run([exe], name + '-test') and ok

inputs = json.loads((root / 'evidence/inputs.json').read_text(encoding='utf-8-sig'))
checks = []
snapshot_checks = []
for item in inputs['files']:
    snapshot = root / 'input' / item['path']
    snapshot_checks.append({'path': item['path'], 'unchanged':
        before.get(snapshot.relative_to(root).as_posix()) == item['sha256']})
    p = Path(args.input_source or inputs['source']) / item['path']
    digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    checks.append({'path': str(p), 'expected': item['sha256'], 'actual': digest,
                   'unchanged': digest == item['sha256']})
after = source_hashes()
ok = all(c['unchanged'] for c in snapshot_checks) and before == after and ok
if args.input_source:
    ok = all(c['unchanged'] for c in checks) and ok
report = {'scope': 'Windows host, mock Wi-Fi and fake sherpa C API; no model or board execution',
          'session_id': os.environ.get('CODEX_THREAD_ID'), 'cwd': str(root),
          'utc': stamp, 'passed': ok, 'runs': records, 'input_checks': checks,
          'snapshot_checks': snapshot_checks, 'sources_unchanged_during_run': before == after,
          'candidate_sha256': before, 'after_sha256': after,
          'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(out / 'result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print('Evidence: ' + str(out))
sys.exit(0 if ok else 1)
