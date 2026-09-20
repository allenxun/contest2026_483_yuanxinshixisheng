"""Compare archive files to independently obtained official source snapshots."""
import hashlib,json
from pathlib import Path
from urllib.parse import urlparse
R=Path(__file__).resolve().parents[1]
B=R/'work-in-progress/native-voice-sources'
C=R/'work-in-progress/parallel-model-reader-medium/native-voice-source-plan-v1'
assert hashlib.sha256((C/'sources.json').read_bytes()).hexdigest()=='b5396f9f60497dee5e7a66a898f4589dbd5b5907575d0b501e1e5481229cc988'
roots={'sherpa-onnx':'sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9',
       'onnxruntime':'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'}
rows=[]
for row in json.loads((C/'sources.json').read_text()):
    url=urlparse(row['url'])
    if url.netloc!='raw.githubusercontent.com':continue
    parts=url.path.strip('/').split('/')
    if parts[1] not in roots:continue
    file=B/roots[parts[1]]/Path(*parts[3:])
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    assert digest==row['sha256'],file
    rows.append(dict(path=str(file.relative_to(B)),sha256=digest,source_url=row['url']))
assert rows
(B/'official-source-crosscheck.json').write_text(json.dumps(dict(passed=True,files=rows,
    compiled=False,scope='selected official build and platform files; full archive inventory recorded separately'),indent=2))
print(len(rows),'official source snapshots match extracted archives')
