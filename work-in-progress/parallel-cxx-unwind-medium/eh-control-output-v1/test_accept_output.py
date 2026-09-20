"""Offline tests; synthesized target-like text is NEVER hardware evidence."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from accept_output import evaluate

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'eh-control-v1'/'host-results.json'

def main():
    data=SOURCE.read_bytes()
    commands=json.loads(data.decode('utf-8'))['commands']
    cases=[]
    def check(name,text,mode,scope,expected,origin):
        result=evaluate(text,mode,scope)
        cases.append(dict(name=name,origin=origin,input=text,input_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                          expected_accept=expected,result=result,passed=result['passed']==expected))
    normal={}
    for i,c in enumerate(commands):
        command=c['command']
        if not command[0].endswith('.exe'): continue
        mode=command[1] if command[1] in ('single','warm1') else 'single'
        check('frozen-command-{}'.format(i),c['output'],mode,'host',c['exit_code']==0,'frozen-host-output')
        if Path(command[0]).name=='normal.exe' and command[1] in ('single','warm1'):
            normal[mode]=c['output']
    assert set(normal)=={'single','warm1'}
    warm=normal['warm1']; single=normal['single']
    lines=warm.splitlines()
    pre=next(x for x in lines if ' PREHEAT_PASS ' in x)
    worker=next(x for x in lines if ' worker=0 ' in x)
    begin=next(x for x in lines if ' begin ' in x)
    final=next(x for x in lines if ' result=' in x)
    mutations={
        'missing-preheat':warm.replace(pre,''),
        'late-preheat':warm.replace(pre,'').replace(worker,worker+'\n'+pre),
        'missing-worker':warm.replace(worker,''),
        'missing-final':warm.replace(final,''),
        'missing-begin':warm.replace(begin,''),
        'duplicate-worker':warm.replace(worker,worker+'\n'+worker),
        'duplicate-preheat':warm.replace(pre,pre+'\n'+pre),
        'duplicate-begin':warm.replace(begin,begin+'\n'+begin),
        'duplicate-final':warm+'\n'+final,
        'wrong-worker-id':warm.replace('worker=1','worker=0'),
        'wrong-caught':warm.replace('caught=1','caught=2'),
        'wrong-cleaned':warm.replace('cleaned=3','cleaned=2'),
        'wrong-errors':warm.replace('errors=0','errors=1'),
        'wrong-created':warm.replace('created=2','created=1'),
        'wrong-joined':warm.replace('joined=2','joined=1'),
        'wrong-requested-cpu':warm.replace('requested_cpu=4','requested_cpu=5'),
        'wrong-cpu-mismatch':warm.replace('cpu_mismatch=0','cpu_mismatch=1'),
        'fail-final':warm.replace('result=PASS','result=FAIL'),
        'crash-after-pass':warm+'\nCPU5 sched_dumpstack abort\n',
        'duplicate-field':warm.replace('errors=0','errors=0 errors=0'),
        'truncated-field':warm.replace('cleaned=3','cleaned='),
        'early-final':final+'\n'+warm.replace(final,''),
        'interleaved':warm.replace(worker,'NSH> '+worker),
        'unexpected-record':warm+'\nK7EHCONTROL REBOOT_REQUIRED\n',
        'wrong-mode':warm.replace('mode=warm1','mode=single'),
    }
    for name,value in mutations.items(): check(name,value,'warm1','host',False,'synthetic-mutation-of-host')
    check('single-unexpected-preheat',single.replace('K7EHCONTROL worker',pre+'\nK7EHCONTROL worker'),'single','host',False,'synthetic-mutation-of-host')
    check('host-not-target',warm,'warm1','target',False,'frozen-host-output-wrong-scope')
    target=re.sub(r'cpu=-1 requested_cpu=(\d+)',r'cpu=\1 requested_cpu=\1',warm)
    check('synthetic-target-good',target,'warm1','target',True,'synthetic-target-like-NOT-HARDWARE')
    check('synthetic-target-wrong-cpu',target.replace('cpu=4 requested_cpu','cpu=5 requested_cpu'),'warm1','target',False,'synthetic-target-like-NOT-HARDWARE')
    check('target-not-host',target,'warm1','host',False,'synthetic-target-like-NOT-HARDWARE')
    check('serial-background-and-crlf','nsh> k7ehcontrol warm1\r\n'+warm.replace('\n','\r\n')+'nsh>\r\n','warm1','host',True,'synthetic-serial-envelope-host')
    check('bad-clock',re.sub(r'first_end=\d+','first_end=0',warm),'warm1','host',False,'synthetic-mutation-of-host')
    for mode,raw in normal.items():
        (HERE/('host-'+mode+'.txt')).write_text(raw,encoding='utf-8')
    cli=[]
    for scope,expected in [('host',0),('target',1)]:
        command=[sys.executable,'-B',str(HERE/'accept_output.py'),str(HERE/'host-warm1.txt'),'--mode','warm1','--scope',scope]
        proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
        cli.append(dict(command=command,exit_code=proc.returncode,expected=expected,output=proc.stdout,passed=proc.returncode==expected))
    report=dict(source=str(SOURCE),source_sha256=hashlib.sha256(data).hexdigest(),cases=cases,cli=cli,
                case_count=len(cases),all_passed=all(x['passed'] for x in cases+cli),hardware_tested=False)
    (HERE/'test-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for c in cases: print(('PASS' if c['passed'] else 'FAIL')+' '+c['name'])
    print('cases={} cli={} all_passed={} hardware_tested=False'.format(len(cases),len(cli),report['all_passed']))
    return 0 if report['all_passed'] else 1

if __name__=='__main__': sys.exit(main())
