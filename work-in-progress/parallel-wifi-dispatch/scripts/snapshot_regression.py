from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
p=R/'input/sources.json';rows=json.loads(p.read_text(encoding='utf8'))
source=R.parent/'parallel-wifi-service/tests/test_broker.c';data=source.read_bytes()
dest=R/'tests/test_broker.c'
with dest.open('xb') as f:f.write(data)
rows.append(dict(source=str(source),copy=str(dest.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
p.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
