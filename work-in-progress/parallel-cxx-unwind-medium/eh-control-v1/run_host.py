"""Strict builds and control/output tests, host only."""
import hashlib
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
records=[]
def run(cmd,expected=0,contains=(),absent=()):
    try:
        p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
        code=p.returncode; text=p.stdout.decode('utf-8','replace')
    except subprocess.TimeoutExpired as e:
        code=-999; text=(e.stdout or b'').decode('utf-8','replace')+'\nHOST_TIMEOUT'
    ok=code==expected and all(x in text for x in contains) and all(x not in text for x in absent)
    records.append(dict(command=cmd,exit_code=code,expected=expected,output=text,
                        expected_text=list(contains),absent_text=list(absent),passed=ok))
    return ok
run(['g++','-v'])
variants=[('normal',[]),('fail0',['-DK7EH_FAIL_CREATE=0']),('fail1',['-DK7EH_FAIL_CREATE=1']),
          ('slow',['-DK7EH_SLOW_READY']),('count',['-DK7EH_BAD_COUNT'])]
for name,flags in variants:
    exe=str(HERE/(name+'.exe'))
    if not run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread','-DK7EH_HOST_TEST']+flags+['k7ehcontrol_main.cxx','-o',exe]): continue
    if name=='normal':
        run([exe,'single'],contains=['mode=single rounds=1 workers=1 main_prethrow=0','worker=0 caught=1 cleaned=3 errors=0',
                                   'requested_cpu=5','created=1 joined=1'],absent=['PREHEAT_PASS','worker=1'])
        run([exe,'warm1'],contains=['mode=warm1 rounds=1 workers=2 main_prethrow=1',
                                  'PREHEAT_PASS caught=1 cleaned=3 workers_created=0',
                                  'worker=0 caught=1 cleaned=3 errors=0','worker=1 caught=1 cleaned=3 errors=0',
                                  'requested_cpu=4','requested_cpu=5','created=2 joined=2'])
        text=records[-1]['output']
        records[-1]['preheat_before_worker_output']=text.find('PREHEAT_PASS')<text.find('K7EHCONTROL worker=')
        records[-1]['passed'] &= records[-1]['preheat_before_worker_output']
        run([exe,'repeat'],2,contains=['already attempted; reboot required'])
        run([exe,'cold'],1,contains=['usage: k7ehcontrol'])
    elif name=='fail0':
        run([exe,'single'],20,contains=['create_failed index=0','created=0 joined=0'],absent=['PREHEAT_PASS'])
    elif name=='fail1':
        run([exe,'single'],contains=['created=1 joined=1'],absent=['create_failed'])
        run([exe,'warm1'],20,contains=['PREHEAT_PASS','create_failed index=1','created=1 joined=1'])
    elif name=='slow':
        run([exe,'warm1'],21,contains=['PREHEAT_PASS','created=2 joined=2','result=FAIL'])
    elif name=='count':
        run([exe,'warm1'],22,contains=['PREHEAT_PASS','worker=1 caught=1 cleaned=4','created=2 joined=2'])
result=dict(commands=records,all_passed=all(x['passed'] for x in records),
            source_sha256=hashlib.sha256((HERE/'k7ehcontrol_main.cxx').read_bytes()).hexdigest(),
            scope='Windows GCC12.2 POSIX-thread SEH: control logic and stdout only; no target unwind safety proof',
            target_compiled=False,hardware_tested=False)
(HERE/'host-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(all_passed=result['all_passed'],commands=len(records)),indent=2))
raise SystemExit(0 if result['all_passed'] else 1)
