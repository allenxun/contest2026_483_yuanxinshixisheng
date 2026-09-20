import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
COMPILER = Path('D:/software/mingw64/mingw64/bin/g++.exe')
environment = dict(os.environ)
environment['PATH'] = str(COMPILER.parent) + os.pathsep + environment['PATH']
records = []
for opt in ('-O0', '-O2'):
    for stage, source in (
            ('before', HERE / 'input/native_asr_runtime.cpp'),
            ('after', PROJECT / 'app/voicelink/src/native_asr_runtime.cpp')):
        exe = HERE / (stage + opt + '.exe')
        command = [str(COMPILER), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                   '-pthread', opt, '-I' + str(HERE),
                   '-I' + str(PROJECT / 'app/voicelink/include'),
                   '-I' + str(PROJECT / 'work-in-progress/parallel-voicelink/vendor'),
                   str(source), str(HERE / 'test_runtime.cpp'), '-o', str(exe)]
        subprocess.run(command, check=True, env=environment, timeout=60)
        r = subprocess.run([str(exe)], env=environment, timeout=30, capture_output=True)
        assert r.returncode == 0
        (HERE / (stage + opt + '.log')).write_bytes(r.stdout + r.stderr)
        leaked = b'ASR_PRIVATE_TEST_TOKEN' in r.stdout + r.stderr
        assert leaked == (stage == 'before')
        records.append({'stage': stage, 'optimization': opt,
                        'functional_exit': r.returncode, 'logged_transcript': leaked,
                        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
(HERE / 'runtime-test.json').write_text(json.dumps(records, indent=2))
print('PASS: bounded outputs, frame limits, cleanup, concurrency and transcript logging checks O0/O2')
