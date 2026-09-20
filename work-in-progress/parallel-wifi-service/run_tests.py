"""Host-only C/C++ tests; all outputs remain below this task directory."""
import datetime, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parent
out=root/'evidence'/('run-'+datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir()
def hashes():
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('src','include','tests','input') for p in sorted((root/folder).rglob('*')) if p.is_file()}
before=hashes(); records=[]
cc=shutil.which('gcc');cxx=shutil.which('g++')
env=os.environ.copy();env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','') if cc else env.get('PATH','')
def run(cmd,name):
    try:
        p=subprocess.run(cmd,cwd=str(root),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
        raw,code=p.stdout,p.returncode
    except subprocess.TimeoutExpired as e: raw,code=e.output or b'',124
    except OSError as e: raw,code=str(e).encode(),125
    (out/(name+'.raw')).write_bytes(raw)
    (out/(name+'.txt')).write_text(raw.decode('utf-8',errors='replace'),encoding='utf-8')
    records.append({'command':cmd,'name':name,'exit_code':code});print(name,code)
    if raw: print(raw.decode('utf-8',errors='replace'))
    return code==0
ok=bool(cc and cxx)
if ok:
    ok=run([cc,'--version'],'compiler') and ok
    flags=['-O2','-Wall','-Wextra','-Wpedantic','-Werror','-Iinclude']
    obj=str(out/'broker.o');exe=str(out/'test_broker.exe');adapt=str(out/'test_adapter.exe')
    built=run([cc,'-std=c11']+flags+['-c','src/wifi_broker.c','-o',obj],'core-build');ok=built and ok
    if built:
        linked=run([cc,'-std=c11']+flags+['tests/test_broker.c',obj,'-o',exe],'broker-build');ok=linked and ok
        if linked:ok=run([exe],'broker-test') and ok
        linked=run([cxx,'-std=c++17','-finput-charset=UTF-8','-fexec-charset=UTF-8']+flags+
          ['-Iinput/work-in-progress/parallel-voicelink/include','tests/test_adapter.cpp',obj,'-o',adapt],'adapter-build');ok=linked and ok
        if linked:ok=run([adapt],'adapter-test') and ok
inputs=json.loads((root/'evidence/inputs.json').read_text(encoding='utf-8-sig'))
checks=[]
for f in inputs['files']:
    p=Path(inputs['source'])/f['path'];snapshot=root/'input'/f['path']
    checks.append({'path':f['path'],'source_unchanged':p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'],
                   'snapshot_unchanged':hashlib.sha256(snapshot.read_bytes()).hexdigest()==f['sha256']})
after=hashes();ok=ok and before==after and all(c['source_unchanged'] and c['snapshot_unchanged'] for c in checks)
report={'passed':ok,'scope':'Windows host; simulated backend; no hardware/SDK/network calls',
        'session_id':os.environ.get('CODEX_THREAD_ID'),'cwd':str(root),'runs':records,
        'inputs':checks,'before':before,'after':after,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(out);sys.exit(0 if ok else 1)
