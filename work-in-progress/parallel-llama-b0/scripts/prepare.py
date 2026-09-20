from pathlib import Path
import hashlib,json,urllib.request,tarfile,datetime
R=Path(__file__).resolve().parents[1]
rev='74d4f5b041ad837153b0e90fc864b8290e01d8d5'
url='https://codeload.github.com/ggml-org/llama.cpp/tar.gz/'+rev
archive=R/'input'/('llama-'+rev+'.tar.gz')
if not archive.exists():
    with urllib.request.urlopen(url,timeout=60) as f,archive.open('xb') as out:
        while data:=f.read(1024*1024):out.write(data)
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='8dd9fcc7c17f972673960ffdcc7521f52de5a9ec594aa6acebd9dfd8c17c0a5c'
dest=R/'vendor'
dest.mkdir(exist_ok=True)
assert not (dest/('llama.cpp-'+rev)).exists(), 'source exists; verify rather than overwrite'
with tarfile.open(archive) as t:
    for m in t.getmembers():
        p=(dest/m.name).resolve()
        assert p.is_relative_to(dest.resolve())
    t.extractall(dest,filter='data')
rows=[]
project=R.parents[1]
for name in ['docs/离线Agent选型与B0落地方案_20260910.md','config/agent-offline-probe.example.json','artifacts/smp-load-20260910/.config']:
    p=project/name;data=p.read_bytes();out=R/'input'/name;out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('xb') as f:f.write(data)
    rows.append(dict(source=str(p),copy=str(out.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
(R/'input/sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
(R/'VERSION.json').write_text(json.dumps(dict(repository='https://github.com/ggml-org/llama.cpp',tag='b5046',commit=rev,
    archive_url=url,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),fetched_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    weights_downloaded=False),indent=2),encoding='utf8')
print('source_ready',rev,archive.stat().st_size)
