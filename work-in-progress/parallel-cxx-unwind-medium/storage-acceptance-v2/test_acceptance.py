"""All captures and identity documents in these tests are explicitly synthetic."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from accept_storage import evaluate,sha
HERE=Path(__file__).resolve().parent
FIX=HERE/'synthetic'; FIX.mkdir(exist_ok=True)
captures={
 'before':b'k7storage list\r\nUSB_STORAGE nodes=0\r\nUSB_STORAGE command=list result=0 mount_attempted=0\r\nnsh> \x1b[K',
 'start':b'k7storage start\r\nK7 host: initializing\r\nUSB_STORAGE command=start result=0 mount_attempted=0\r\nnsh> ',
 'after':b'k7storage list\r\nUSB_STORAGE node=/dev/sda\r\nUSB_STORAGE nodes=1\r\nUSB_STORAGE command=list result=0 mount_attempted=0\r\nnsh> ',
 'read':b'k7storage read /dev/sda\r\nUSB_STORAGE read node=/dev/sda sector_size=512 sectors=1000 readonly=1 lba=0 reads=2 crc32=12345678 repeated=1 boot_signature=1 exfat_oem=0\r\nUSB_STORAGE command=read result=0 mount_attempted=0\r\nnsh> ',
}
for key,data in captures.items(): (FIX/(key+'.bin')).write_bytes(data)
for name in ('enumeration','build'):
    (FIX/(name+'.txt')).write_text('SYNTHETIC '+name+' placeholder for policy tests; NOT HARDWARE\n',encoding='utf-8')
source=json.loads((HERE/'input.json').read_text(encoding='utf-8'))
identity=dict(scope='synthetic',evidence_origin='synthetic',node='/dev/sda',vid='1234',pid='5678',
              run_id='SYNTHETIC-RUN-1',ordered_phases=['before','start','after','read'],identity_reviewed=True,
              reviewer='synthetic test fixture',source_sha256=source['source_sha256'],firmware_sha256='0'*64,
              capture_sha256={k:sha(v) for k,v in captures.items()},
              enumeration_evidence=dict(path='enumeration.txt',sha256=sha((FIX/'enumeration.txt').read_bytes())),
              build_evidence=dict(path='build.txt',sha256=sha((FIX/'build.txt').read_bytes())))
(FIX/'identity.json').write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')
cases=[]
def check(name,caps,ident,expected,scope='synthetic'):
    result=evaluate(caps,'/dev/sda',scope,ident,FIX)
    cases.append(dict(name=name,synthetic=True,expected=expected,result=result,passed=result['passed']==expected,
                      captures={k:v.decode('utf-8','backslashreplace') for k,v in caps.items()},identity=ident))
def mutated(name,key,old,new):
    caps=captures.copy();caps[key]=caps[key].replace(old,new)
    ident=copy.deepcopy(identity);ident['capture_sha256']={k:sha(v) for k,v in caps.items()}
    check(name,caps,ident,False)
check('valid-synthetic',captures,identity,True)
for name,key,old,new in [
 ('close-failure','read',b'command=read result=0',b'command=read result=-5'),
 ('missing-final','read',b'USB_STORAGE command=read result=0 mount_attempted=0\r\n',b''),
 ('missing-prompt','read',b'nsh> ',b''),
 ('missing-echo','read',b'k7storage read /dev/sda\r\n',b''),
 ('one-read','read',b'reads=2',b'reads=1'),
 ('mismatch-data','read',b'repeated=1',b'repeated=0'),
 ('writable','read',b'readonly=1',b'readonly=0'),
 ('wrong-node','read',b'node=/dev/sda',b'node=/dev/sdb'),
 ('wrong-lba','read',b'lba=0',b'lba=1'),
 ('bad-size','read',b'sector_size=512',b'sector_size=513'),
 ('zero-capacity','read',b'sectors=1000',b'sectors=0'),
 ('overflow-capacity','read',b'sectors=1000',b'sectors=4294967296'),
 ('bad-crc','read',b'crc32=12345678',b'crc32=1234'),
 ('duplicate-field','read',b'reads=2',b'reads=2 reads=2'),
 ('fault-after-summary','read',b'USB_STORAGE command=read',b'CPU5 abort sched_dumpstack\r\nUSB_STORAGE command=read'),
 ('truncated-record','read',b'USB_STORAGE command=read',b'USB_STOR\r\nUSB_STORAGE command=read'),
 ('mount-attempted','read',b'mount_attempted=0',b'mount_attempted=1'),
 ('old-read-mixed','read',b'nsh> ',captures['read']),
 ('old-list-mixed','after',b'nsh> ',captures['after']),
 ('duplicate-node','after',b'USB_STORAGE nodes=1',b'USB_STORAGE node=/dev/sda\r\nUSB_STORAGE nodes=2'),
 ('wrong-node-count','after',b'nodes=1',b'nodes=2'),
 ('node-not-new','before',b'USB_STORAGE nodes=0',b'USB_STORAGE node=/dev/sda\r\nUSB_STORAGE nodes=1'),
 ('ambiguous-new-node','after',b'USB_STORAGE nodes=1',b'USB_STORAGE node=/dev/sdb\r\nUSB_STORAGE nodes=2'),
 ('start-failed','start',b'result=0',b'result=-5'),
 ('list-failed','before',b'result=0',b'result=-5'),
 ('bad-utf8','read',b'crc32=',b'\xffcrc32='),
 ('interleaved-record','read',b'USB_STORAGE read',b'DMA USB_STORAGE read'),
]: mutated(name,key,old,new)
for key,value in [('capture_sha256',{}),('source_sha256','0'*64),('node','/dev/sdb'),('vid',''),
                  ('identity_reviewed',False),('ordered_phases',[]),('enumeration_evidence',{}),('build_evidence',{})]:
    ident=copy.deepcopy(identity);ident[key]=value;check('identity-'+key,captures,ident,False)
check('synthetic-cannot-be-target',captures,identity,False,'target')
# Exact C-agent host-output fragments, with explicitly synthetic shell framing.
host=(HERE/'candidate-host.stdout.frozen').read_bytes().replace(b'\r\n',b'\n')
for name,fragment in [
 ('candidate-list-open-failed',b'USB_STORAGE command=list result=-5 mount_attempted=0\n'),
 ('candidate-list-read-or-close-failed',b'USB_STORAGE nodes=0\nUSB_STORAGE command=list result=-5 mount_attempted=0\n'),
 ('candidate-list-256-limit',b'USB_STORAGE node=/dev/sda\nUSB_STORAGE nodes=1\nUSB_STORAGE command=list result=-7 mount_attempted=0\n'),
]:
    assert fragment in host
    caps=captures.copy();caps['after']=b'k7storage list\n'+fragment+b'nsh> '
    ident=copy.deepcopy(identity);ident['capture_sha256']={k:sha(v) for k,v in caps.items()}
    check(name,caps,ident,False)
ident=copy.deepcopy(identity)
ident['source_sha256']='a3a13309f71306a16490a3a2410138b2219638cf76041f2826fea88a5a04d9a4'
check('old-v1-source-binding-rejected',captures,ident,False)
cli=[]
for scope,expected in [('synthetic',0),('target',1)]:
    command=[sys.executable,'-B',str(HERE/'accept_storage.py'),'--node','/dev/sda','--scope',scope,'--identity',str(FIX/'identity.json')]
    for key in captures: command.extend(['--'+key,str(FIX/(key+'.bin'))])
    p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
    cli.append(dict(command=command,exit_code=p.returncode,expected=expected,output=p.stdout,passed=p.returncode==expected))
report=dict(cases=cases,cli=cli,all_passed=all(c['passed'] for c in cases+cli),target_captures_tested=False)
(HERE/'test-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('cases={} cli={} all_passed={} synthetic_only=True'.format(len(cases),len(cli),report['all_passed']))
raise SystemExit(not report['all_passed'])
