import hashlib
import json
from pathlib import Path
import subprocess
import os
here = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if os.name == 'nt':
    root = here.parents[1]
    header = root / 'work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9'
    records = []
    for opt in ('-O0', '-O2'):
        exe = here / ('test' + opt + '.exe')
        cmd = ['D:/software/mingw64/mingw64/bin/g++.exe', '-std=c++17', opt, '-Wall', '-Wextra', '-Werror', '-pthread',
               '-I' + str(here / 'include'), '-I' + str(header), str(here / 'native_tts_runtime.cpp'), str(here / 'test_runtime.cpp'), '-o', str(exe)]
        subprocess.run(cmd, check=True)
        result = subprocess.run([str(exe)], capture_output=True)
        (here / ('test' + opt + '.log')).write_bytes(result.stdout + result.stderr)
        records.append({'command': cmd, 'exit_code': result.returncode})
        assert result.returncode == 0
    (here / 'host-result.json').write_text(json.dumps(records, indent=2))
else:
    prior = here.parent / 'asr-fixed-fixture-20260913/result.json'
    cmd = json.loads(prior.read_text(encoding='utf-8-sig'))['compile'][0]['command']
    cmd[cmd.index('-c') + 1] = str(here / 'native_tts_runtime.cpp')
    obj = here / 'native_tts_runtime.o'
    cmd[cmd.index('-o') + 1] = str(obj)
    cmd += ['-I' + str(here / 'include')]
    result = subprocess.run(cmd, capture_output=True, timeout=180)
    (here / 'arm64.log').write_bytes(result.stdout + result.stderr)
    (here / 'arm64-result.json').write_text(json.dumps({'command': cmd, 'exit_code': result.returncode,
        'source_sha256': sha(here / 'native_tts_runtime.cpp'),
        'object_sha256': sha(obj) if result.returncode == 0 else None,
        'linked': False, 'board_tested': False}, indent=2))
    assert result.returncode == 0, result.stderr.decode(errors='replace')
print('PASS')
