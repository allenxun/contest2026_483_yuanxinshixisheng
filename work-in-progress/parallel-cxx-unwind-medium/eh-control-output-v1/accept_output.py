"""Strict offline parser for one k7ehcontrol single/warm1 invocation."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PREFIX='K7EHCONTROL '
ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
FAILURE=re.compile(r'\b(?:abort|panic|assertion|backtrace|sched_dumpstack|segmentation fault)\b',re.I)

def evaluate(text,mode,scope):
    if mode not in ('single','warm1') or scope not in ('host','target'):
        raise ValueError('mode single|warm1 and scope host|target are mandatory')
    errors=[]; begins=[]; preheats=[]; workers=[]; finals=[]
    def fail(message): errors.append(message)
    for number,raw in enumerate(text.splitlines(),1):
        line=ANSI.sub('',raw).strip()
        if FAILURE.search(line): fail('line {}: crash diagnostic'.format(number))
        if not line.startswith(PREFIX):
            if PREFIX in line: fail('line {}: malformed/interleaved probe record'.format(number))
            continue
        body=line[len(PREFIX):]
        if body.startswith('begin '): kind='begin'; body=body[6:]
        elif body.startswith('PREHEAT_PASS '): kind='preheat'; body=body[13:]
        elif body.startswith('worker='): kind='worker'
        elif body.startswith('result='): kind='final'
        else:
            fail('line {}: failure or unknown probe record: {}'.format(number,body))
            continue
        fields={}; malformed=False
        for token in body.split():
            if token.count('=')!=1:
                malformed=True; continue
            key,value=token.split('=',1)
            if key in fields or not value: malformed=True
            fields[key]=value
        if malformed:
            fail('line {}: malformed/duplicate fields'.format(number)); continue
        {'begin':begins,'preheat':preheats,'worker':workers,'final':finals}[kind].append((number,fields))
    active=1 if mode=='single' else 2
    if len(begins)!=1: fail('expected exactly one begin')
    if len(finals)!=1: fail('expected exactly one result')
    if len(workers)!=active: fail('worker record count mismatch')
    if len(preheats)!=(1 if mode=='warm1' else 0): fail('preheat marker count mismatch')
    expected_begin=dict(mode=mode,rounds='1',workers=str(active),main_prethrow=str(int(mode=='warm1')))
    if len(begins)==1 and begins[0][1]!=expected_begin: fail('begin fields mismatch')
    expected_final=dict(result='PASS',code='0',created=str(active),joined=str(active),mode=mode,concurrency_proven='0')
    if len(finals)==1 and finals[0][1]!=expected_final: fail('result/created/joined fields mismatch')
    if preheats and preheats[0][1]!=dict(caught='1',cleaned='3',workers_created='0'):
        fail('preheat fields mismatch')
    parsed=[]; ids=[]
    keys={'worker','caught','cleaned','errors','cpu','requested_cpu','cpu_mismatch','first_begin','first_end'}
    for number,f in workers:
        if set(f)!=keys:
            fail('line {}: worker field set mismatch'.format(number)); continue
        try:
            if not all(re.fullmatch(r'-?\d+',v) for v in f.values()): raise ValueError()
            values={k:int(v) for k,v in f.items()}
        except ValueError:
            fail('line {}: noninteger worker field'.format(number)); continue
        i=values['worker']; ids.append(i); parsed.append(values)
        requested=5 if mode=='single' else 4+i
        if not 0<=i<active: fail('worker id outside expected range')
        if values['caught']!=1 or values['cleaned']!=3 or values['errors']!=0 or values['cpu_mismatch']!=0:
            fail('worker count/error mismatch')
        if values['requested_cpu']!=requested: fail('requested CPU mismatch')
        if values['cpu']!=(requested if scope=='target' else -1): fail('observed CPU does not match scope/affinity')
        if values['first_begin']<=0 or values['first_end']<values['first_begin']: fail('invalid first-call clock interval')
    if sorted(ids)!=list(range(active)): fail('duplicate or missing worker ids')
    if len(begins)==1 and len(finals)==1:
        start=begins[0][0]; end=finals[0][0]
        if start>=end: fail('result precedes begin')
        for number,_ in workers+preheats:
            if not start<number<end: fail('worker/preheat record outside invocation')
        if mode=='warm1' and len(preheats)==1 and any(n<preheats[0][0] for n,_ in workers):
            fail('worker output precedes PREHEAT_PASS')
    overlap=None
    if len(parsed)==2:
        a,b=parsed
        overlap=max(a['first_begin'],b['first_begin'])<min(a['first_end'],b['first_end'])
    return dict(passed=not errors,mode=mode,scope=scope,errors=errors,workers=parsed,
                record_counts=dict(begin=len(begins),preheat=len(preheats),workers=len(workers),result=len(finals)),
                first_call_intervals_overlap=overlap,libgcc_thread_safety_proven=False,
                global_unwinder_cold_proven=False,hardware_provenance_verified=False,
                interpretation='Text assertions only; scope is supplied by caller, not authenticated hardware origin')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('input',type=Path)
    p.add_argument('--mode',required=True,choices=['single','warm1'])
    p.add_argument('--scope',required=True,choices=['host','target'])
    p.add_argument('--output',type=Path); a=p.parse_args()
    data=a.input.read_bytes()
    result=evaluate(data.decode('utf-8','replace'),a.mode,a.scope)
    result.update(input_sha256=hashlib.sha256(data).hexdigest(),input_bytes=len(data))
    rendered=json.dumps(result,indent=2)
    if a.output: a.output.write_text(rendered+'\n',encoding='utf-8')
    print(rendered)
    raise SystemExit(0 if result['passed'] else 1)
