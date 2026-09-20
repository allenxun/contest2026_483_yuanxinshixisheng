"""Bounded local host-only test; never touches device or SDK."""
from pathlib import Path
import datetime, hashlib, json, os, subprocess, time
R = Path(__file__).resolve().parents[1]
GCC = Path(os.environ.get('WD_GCC', r'D:\software\mingw64\mingw64\bin\gcc.exe'))
out = R/'evidence'/datetime.datetime.now(datetime.timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ')
out.mkdir(parents=True)
env = dict(os.environ, PATH=str(GCC.parent)+os.pathsep+os.environ.get('PATH',''))
records = []
def run(name, cmd):
    started = time.monotonic()
    try:
        p = subprocess.run([str(x) for x in cmd], cwd=R, env=env, capture_output=True, timeout=30)
        data = p.stdout+p.stderr
        rc = p.returncode
    except subprocess.TimeoutExpired as e:
        data = (e.stdout or b'')+(e.stderr or b'')+b'\nTIMEOUT\n'
        rc = -1
    (out/(name+'.log')).write_bytes(data)
    records.append(dict(name=name, command=[str(x) for x in cmd], returncode=rc,
                        seconds=time.monotonic()-started, log=name+'.log',
                        log_sha256=hashlib.sha256(data).hexdigest()))
    assert b'!WD.secret#123' not in data, 'credential appeared in output'
    assert rc == 0, name+' failed; retained evidence'
try:
    run('compiler', [GCC, '--version'])
    for opt in ('O0','O2'):
        binary = out/('test-'+opt+'.exe')
        run('compile-'+opt, [GCC, '-std=c11','-'+opt,'-Wall','-Wextra','-Werror',
            '-Wconversion','-Wshadow','-pedantic','-pthread','-I','include',
            'src/wifi_broker.c','src/wifi_dispatch.c','tests/test_dispatch.c','-o',binary])
        run('test-'+opt, [binary])
    binary=out/'broker-regression.exe'
    run('compile-broker-regression',[GCC,'-std=c11','-O2','-Wall','-Wextra','-Werror',
        '-I','include','src/wifi_broker.c','tests/test_broker.c','-o',binary])
    run('test-broker-regression',[binary])
    inputs=[]
    for row in json.loads((R/'input/sources.json').read_text(encoding='utf8')):
        p=Path(row['source']); current=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        inputs.append(dict(**row,current_sha256=current,unchanged=current==row['sha256']))
    (out/'input-verification.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf8')
finally:
    files=[dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
           for folder in ('include','src','tests','scripts') for p in sorted((R/folder).glob('*')) if p.is_file()]
    (out/'result.json').write_text(json.dumps(dict(host_only=True, simulated_clock=True,
        process_timeout_seconds=30,commands=records,files=files),ensure_ascii=False,indent=2),encoding='utf8')
print(str(out))
