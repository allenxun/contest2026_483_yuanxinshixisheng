from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
p=R/'input/sources.json';rows=json.loads(p.read_text(encoding='utf8'))
for name in ('wifi_assoc_probe.inc','wifi_auth_console.inc'):
    source=R.parents[1]/'app/k7radio'/name
    data=source.read_bytes();dest=R/'input/k7radio'/name
    with dest.open('xb') as f:f.write(data)
    rows.append(dict(source=str(source),copy=str(dest.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
p.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
