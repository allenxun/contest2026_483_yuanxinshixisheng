"""Read-only validation of parent-captured serial evidence, not device access."""
import hashlib
import json
from pathlib import Path
from accept_output import evaluate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
cases=[]
for relative,mode,expected in [
    ('evidence/eh-control-20260910/single/runtime.bin','single',True),
    ('evidence/eh-control-20260910/warm1/runtime.bin','warm1',True),
    ('evidence/cxx-eh-20260910/cold/runtime.bin','warm1',False),
]:
    p=ROOT/relative; data=p.read_bytes()
    result=evaluate(data.decode('utf-8','replace'),mode,'target')
    cases.append(dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                      expected_accept=expected,result=result,passed=result['passed']==expected,
                      origin='parent-captured serial file; no independent hardware provenance verification'))
report=dict(cases=cases,all_passed=all(c['passed'] for c in cases),
            note='Original cxx-eh cold is an older protocol and crash rejection example, not an eh-control invocation. No files modified, no device access.')
(HERE/'target-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['all_passed'] else 1)
