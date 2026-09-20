"""Verify the two handed-off candidates, without running their code or models."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
records=[]
for name in ('parallel-wifi-service','parallel-voicelink-runtime'):
    base=R/'work-in-progress'/name
    delivery=json.loads((base/'evidence/delivery.json').read_text(encoding='utf-8'))
    for rel,digest in delivery['files'].items():
        p=(base/rel).resolve();assert p.is_relative_to(base) and sha(p)==digest,rel
    if name=='parallel-wifi-service':
        inputs=json.loads((base/'evidence/inputs.json').read_text(encoding='utf-8'))
        for item in inputs['files']:
            assert sha(R/item['path'])==item['sha256'],item['path']
            assert sha(base/'input'/item['path'])==item['sha256'],item['path']
        report=json.loads((base/delivery['tests']).read_text(encoding='utf-8'))
        assert report['passed'] and all(x['exit_code']==0 for x in report['runs'])
        reports=[delivery['tests']]
    else:
        for item in delivery['inputs_unchanged']:
            p=Path(item['path']);assert p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],item['path']
        reports=delivery['reports']
        for rel in reports:
            report=json.loads((base/rel).read_text(encoding='utf-8'))
            assert report['exit_code']==0 and not report['timed_out'],rel
    records.append(dict(candidate=name,delivery_sha256=sha(base/'evidence/delivery.json'),
        files_verified=len(delivery['files']),reports={p:sha(base/p) for p in reports},
        scope='Recorded Windows evidence and current hashes verified; no rerun or board integration',
        board_integrated=False))
out=R/'evidence/voicelink-handoff-20260910/followups.json'
out.write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
print(json.dumps(records))
