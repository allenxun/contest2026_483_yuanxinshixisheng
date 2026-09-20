from pathlib import Path
import hashlib,json,tarfile
R=Path(__file__).resolve().parents[1]
rev='74d4f5b041ad837153b0e90fc864b8290e01d8d5';source=R/'vendor'/('llama.cpp-'+rev)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
with tarfile.open(R/'input'/('llama-'+rev+'.tar.gz')) as t:
    for item in t.getmembers():
        if not item.isfile():continue
        p=R/'vendor'/item.name;expect=hashlib.sha256(t.extractfile(item).read()).hexdigest()
        actual=sha(p)
        assert actual==expect,str(p)
        rows.append(dict(path=str(p.relative_to(R)),sha256=actual,bytes=p.stat().st_size))
(R/'source-manifest.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
(R/'archive-verification.json').write_text(json.dumps(dict(commit=rev,source_files=len(rows),all_match=True),indent=2),encoding='utf8')
(R/'candidate/LICENSE').write_bytes((source/'LICENSE').read_bytes())
files=[]
for p in sorted(R.rglob('*')):
    if not p.is_file():continue
    rel=p.relative_to(R)
    if rel.parts[0] in ('vendor','tools') or p.name=='delivery.json' or '__pycache__' in rel.parts:continue
    if 'build' in rel.parts and p.suffix not in ('.a','.exe') and p.name not in ('compile_commands.json','CMakeCache.txt','link.txt','linkLibs.rsp'):continue
    if p.name=='objects.a':continue
    files.append(dict(path=str(rel),sha256=sha(p),bytes=p.stat().st_size))
(R/'delivery.json').write_text(json.dumps(dict(session_id='01a0892e-2964-7ec3-bd76-9ab4937980cb',
    exclusions='vendor covered by source-manifest and official archive; tools and regenerable build intermediates excluded; delivery excludes itself',
    files=files),ensure_ascii=False,indent=2),encoding='utf8')
print('verified_source_files',len(rows),'delivery_files',len(files))
