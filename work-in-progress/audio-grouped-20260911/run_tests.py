import argparse
import hashlib
import json
import subprocess
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument('--compiler', default=r'D:\software\mingw64\mingw64\bin\gcc.exe')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
here = Path(__file__).resolve().parent
sources = [here / 'test.c', root / 'app/k7sound/pio.c', root / 'app/k7sound/pio.h']
runs = []
for opt in ('O0', 'O2'):
    exe = here / f'grouped-{opt}.exe'
    command = [args.compiler, f'-{opt}', '-std=c11', '-Wall', '-Wextra',
               '-Wpedantic', '-Werror', '-I' + str(root / 'app/k7sound'),
               str(here / 'test.c'), str(root / 'app/k7sound/pio.c'),
               '-o', str(exe)]
    build = subprocess.run(command, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120)
    (here / f'{opt}-build.log').write_bytes(build.stdout)
    if build.returncode:
        raise SystemExit(build.stdout.decode(errors='replace'))
    test = subprocess.run([str(exe)], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=20)
    (here / f'{opt}-test.log').write_bytes(test.stdout)
    if test.returncode:
        raise SystemExit(test.stdout.decode(errors='replace'))
    runs.append({'optimization': opt, 'compile_exit_code': build.returncode,
                 'test_exit_code': test.returncode,
                 'stdout': test.stdout.decode().strip()})

report = {
    'revision': 'audio-grouped-20260911',
    'hardware_tested': False,
    'runs': runs,
    'sources': {str(path.relative_to(root)).replace('\\', '/'):
                hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sources},
}
(here / 'host-result.json').write_text(json.dumps(report, indent=2) + '\n',
                                       encoding='utf-8')
print(json.dumps(report, indent=2))
