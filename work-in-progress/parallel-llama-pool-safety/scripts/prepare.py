from pathlib import Path
import json,hashlib,tarfile
R=Path(__file__).resolve().parents[1];old=R.parent/'parallel-llama-b0'
rev='74d4f5b041ad837153b0e90fc864b8290e01d8d5'
names=['input/llama-'+rev+'.tar.gz','VERSION.json','CMakeLists.txt','HANDOFF.md','DEPENDENCIES.md',
       'candidate/ggml-backend-reg.cpp','candidate/LICENSE']
rows=[]
for name in names:
    p=old/name;data=p.read_bytes();out=R/'input'/name;out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('xb') as f:f.write(data)
    rows.append(dict(source=str(p),copy=str(out.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
archive=R/'input'/names[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='8dd9fcc7c17f972673960ffdcc7521f52de5a9ec594aa6acebd9dfd8c17c0a5c'
dest=R/'vendor';dest.mkdir()
with tarfile.open(archive) as t:t.extractall(dest,filter='data')
for name in ('ggml-backend-reg.cpp','LICENSE'):
    (R/'candidate'/name).write_bytes((R/'input/candidate'/name).read_bytes())
(R/'input/sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
print('snapshotted',len(rows),'no_download')
