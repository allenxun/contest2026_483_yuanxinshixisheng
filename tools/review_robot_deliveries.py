"""Review frozen parallel outputs and record current input drift separately."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'parallel-vision-contract': 'c2cccb6d08abe1fc82fa7dba941b5f066e69b23f37b3cf94540797f2e93c6a7e',
    'parallel-mcu-contract': 'ca8891574c18ff7784b478c71eada5762e55f37e05e621a67164b74e1b9923f7',
    'parallel-robot-tools': '56036755277cc3fc3ee207d7d2f7655c40c1244d1bea462a5281879ebddb2344',
}
report = {'utc': datetime.now(timezone.utc).isoformat(), 'deliveries': [],
          'scope': 'Output integrity and current input drift; no repeated tests or hardware acceptance'}
for name, expected in EXPECTED.items():
    root = ROOT / 'work-in-progress' / name
    raw = (root / 'delivery.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected, name
    index = json.loads(raw)
    items = index.get('files', index.get('outputs'))
    for item in items:
        path = (root / item['path']).resolve()
        assert path.is_relative_to(root)
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item['sha256'], path
        assert 'bytes' not in item or len(data) == item['bytes'], path
    if name == 'parallel-vision-contract':
        inputs = json.loads((root / index['inputs']).read_text(encoding='utf-8'))
    elif name == 'parallel-mcu-contract':
        values = json.loads((root / 'evidence-20260910T065849603780Z/inputs.json').read_text(encoding='utf-8'))
        inputs = [dict(path=x['absolute_path'], sha256=x['sha256']) for x in values.values()]
    else:
        inputs = json.loads((root / 'inputs.json').read_text(encoding='utf-8'))
    drift = []
    for item in inputs:
        path = Path(item['path'])
        current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if current != item['sha256']:
            drift.append(dict(path=str(path), snapshot_sha256=item['sha256'], current_sha256=current))
    report['deliveries'].append(dict(name=name, output_count=len(items), index_sha256=expected,
                                     input_count=len(inputs), current_input_drift=drift))
out = ROOT / 'evidence/robot-contract-review-20260910/review.json'
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False))
