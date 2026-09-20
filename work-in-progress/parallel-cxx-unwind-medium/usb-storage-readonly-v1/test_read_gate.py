"""All transaction fixtures here are synthetic; no media accessed."""
import json
from pathlib import Path
from read_gate import completion_errors,request_errors

base=dict(blocks=100000,blocksize=512,lba=0,count=8,opcode=0x28,cbw_bytes=31,data_bytes=4096,
          csw_bytes=13,signature=0x53425355,cbw_tag=7,csw_tag=7,residue=0,status=0)
cases=[]
def check(name,t,expected):
    errors=completion_errors(t)
    cases.append(dict(name=name,input=t,expected_accept=expected,errors=errors,passed=(not errors)==expected,synthetic=True))
check('bounded-read',base,True)
for name,change in [
    ('short-cbw',dict(cbw_bytes=30)),('short-data',dict(data_bytes=4095)),('short-csw',dict(csw_bytes=12)),
    ('bad-signature',dict(signature=0)),('bad-tag',dict(csw_tag=8)),('residue',dict(residue=1)),
    ('status',dict(status=1)),('write10',dict(opcode=0x2a)),('last-lba-overflow',dict(blocks=0)),
    ('unsupported-capacity16',dict(blocks=0x100000000)),('truncated-blocksize',dict(blocksize=65536)),
    ('negative-lba',dict(lba=-1)),('out-of-media',dict(lba=99999)),('read10-count-wrap',dict(count=65536)),
    ('zero-count',dict(count=0)),('over-limit',dict(count=9)),('lba-wrap',dict(lba=0x100000000))]:
    t=base.copy(); t.update(change); check(name,t,False)
t=base.copy(); t.update(lba=99999,count=1,data_bytes=512); check('last-sector',t,True)
t=base.copy(); t.update(blocksize=4096,count=1,data_bytes=4096); check('4k-sector',t,True)
report=dict(cases=cases,all_passed=all(c['passed'] for c in cases),scope='synthetic policy tests only; driver not patched or tested')
(Path(__file__).resolve().parent/'test-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('cases={} all_passed={} synthetic_only=True'.format(len(cases),report['all_passed']))
raise SystemExit(not report['all_passed'])
