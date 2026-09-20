"""Read-only handoff verification; does not run candidate scripts or models."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
P=R/'work-in-progress/parallel-voicelink'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
delivery=json.loads((P/'evidence/delivery.json').read_text(encoding='utf-8'))
for name,digest in delivery['files'].items():
    path=(P/name).resolve()
    assert path.is_relative_to(P) and sha(path)==digest,name
inputs=json.loads((P/'evidence/inputs.json').read_text(encoding='utf-8'))
for item in inputs['files']:
    assert sha(P/'input'/item['path'])==item['sha256'],item['path']
    assert sha(Path(inputs['source'])/item['path'])==item['sha256'],item['path']
lock=json.loads((P/'vendor/sherpa-onnx/version-lock.json').read_text(encoding='utf-8'))
for name,digest in lock['files'].items():assert sha(P/'vendor/sherpa-onnx'/name)==digest,name
report=json.loads((P/delivery['tests']).read_text(encoding='utf-8'))
assert report['passed'] and all(x['exit_code']==0 and not x['timed_out'] for x in report['runs'])
result=dict(session_id=delivery['session_id'],delivery_sha256=sha(P/'evidence/delivery.json'),
            report=delivery['tests'],report_sha256=sha(P/delivery['tests']),
            delivery_files=len(delivery['files']),original_inputs=len(inputs['files']),
            verified=True,scope='Artifact hashes and recorded host results only; no rerun or board integration',
            integrated=False,hardware_tested=False)
out=R/'evidence/voicelink-handoff-20260910';out.mkdir(exist_ok=True)
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
