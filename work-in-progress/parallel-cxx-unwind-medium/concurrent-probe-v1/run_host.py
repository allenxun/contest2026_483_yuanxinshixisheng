"""Reproduce bounded host logic checks; no target access."""
import hashlib
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
commands=[]
def run(cmd, expected=0):
    try:
        p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
        code=p.returncode
        output=p.stdout.decode('utf-8','replace')
    except subprocess.TimeoutExpired as e:
        code=-999
        output=(e.stdout or b'').decode('utf-8','replace')+'\nHOST HARNESS DEADLINE EXPIRED'
    item={'command':cmd,'exit_code':code,'expected_exit_code':expected,'passed':code==expected,'output':output}
    commands.append(item)
    return code==expected
run(['g++','-v'])
variants=[('normal',[]),('fail0',['-DK7EH_FAIL_CREATE=0']),('fail1',['-DK7EH_FAIL_CREATE=1']),
          ('slow',['-DK7EH_SLOW_READY']),('count',['-DK7EH_BAD_COUNT'])]
for name,flags in variants:
    exe=str(HERE/(name+'.exe'))
    cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-pthread','-DK7EH_HOST_TEST']+flags+['k7eh_main.cxx','-o',exe]
    if run(cmd):
        cases=[('cold',0),('warm',0),('repeat',2),('invalid',1)] if name=='normal' else [('cold',{'fail0':20,'fail1':20,'slow':21,'count':22}[name])]
        for mode,expected in cases:
            run([exe,mode],expected)
inputs=['app/k7cxx/k7cxx_main.cxx','app/k7smp/k7smp_main.c',
        'work-in-progress/parallel-cxx-unwind-medium/THREADING-RISK.md']
report={'commands':commands,'all_expected':all(x['passed'] for x in commands),
        'input_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
        'source_sha256':hashlib.sha256((HERE/'k7eh_main.cxx').read_bytes()).hexdigest(),
        'scope':'Windows x86_64 MinGW POSIX-thread SEH runtime; logic checks only; not ARM64 libgcc single-thread validation',
        'sdk_accessed':False,'target_compiled':False,'hardware_tested':False}
(HERE/'host-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'all_expected':report['all_expected'],'command_count':len(commands)},indent=2))
raise SystemExit(0 if report['all_expected'] else 1)
