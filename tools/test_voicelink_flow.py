"""Compile the formal VoiceLink core and run complete text-only flows."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app/voicelink'


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(APP.rglob('*')) if p.suffix in ('.hpp', '.cpp')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', default='D:/software/mingw64/mingw64/bin/g++.exe')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'evidence/voicelink-core-integration-20260910' / ('run-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['PATH'] = str(Path(args.compiler).parent) + os.pathsep + env.get('PATH', '')
    result = {'hardware_tested': False, 'scope': 'formal C++ core, simulated audio/Wi-Fi',
              'source_before': hashes(), 'steps': []}
    try:
        for opt in ('O0', 'O2'):
            binary = out / ('flow-' + opt + '.exe')
            command = [args.compiler, '-std=c++17', '-' + opt, '-Wall', '-Wextra',
                       '-Wpedantic', '-Werror', '-finput-charset=UTF-8', '-fexec-charset=UTF-8',
                       '-I' + str(APP / 'include'), str(APP / 'src/core.cpp'),
                       str(APP / 'src/parsers.cpp'), str(APP / 'tests/test_flow.cpp'),
                       '-o', str(binary)]
            for name, cmd in (('compile-' + opt, command), ('run-' + opt, [str(binary)])):
                step = {'name': name, 'argv': cmd}
                result['steps'].append(step)
                try:
                    proc = subprocess.run(cmd, cwd=out, env=env,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE,
                                          timeout=60)
                    (out / (name + '.stdout')).write_bytes(proc.stdout)
                    (out / (name + '.stderr')).write_bytes(proc.stderr)
                    step['exit_code'] = proc.returncode
                    if proc.returncode:
                        raise RuntimeError(name + ' failed; see raw evidence')
                except subprocess.TimeoutExpired as exc:
                    step['timed_out'] = True
                    (out / (name + '.stdout')).write_bytes(exc.stdout or b'')
                    (out / (name + '.stderr')).write_bytes(exc.stderr or b'')
                    raise
        result['passed'] = True
    except Exception as exc:
        result['passed'] = False
        result['error'] = str(exc)
    finally:
        result['source_after'] = hashes()
        result['source_unchanged'] = result['source_before'] == result['source_after']
        result['passed'] = result.get('passed', False) and result['source_unchanged']
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'evidence': str(out)}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
