from pathlib import Path
import hashlib,json,tarfile
R=Path(__file__).resolve().parents[1];rev='74d4f5b041ad837153b0e90fc864b8290e01d8d5'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sources=[]
with tarfile.open(R/'input/input'/('llama-'+rev+'.tar.gz')) as t:
    for member in t.getmembers():
        if not member.isfile():continue
        p=R/'vendor'/member.name;expected=hashlib.sha256(t.extractfile(member).read()).hexdigest()
        assert sha(p)==expected,str(p)
        sources.append(dict(path=str(p.relative_to(R)),sha256=expected))
(R/'source-manifest.json').write_text(json.dumps(sources,indent=2),encoding='utf8')
(R/'archive-verification.json').write_text(json.dumps(dict(commit=rev,source_files=len(sources),all_match=True),indent=2),encoding='utf8')
rows=[]
for p in sorted(R.rglob('*')):
    if not p.is_file():continue
    rel=p.relative_to(R)
    if rel.parts[0]=='vendor' or p.name=='delivery.json' or '__pycache__' in rel.parts:continue
    if 'build' in rel.parts and p.suffix not in ('.a','.exe') and p.name not in ('compile_commands.json','CMakeCache.txt','link.txt','linkLibs.rsp'):continue
    if p.name=='objects.a':continue
    rows.append(dict(path=str(rel),sha256=sha(p),bytes=p.stat().st_size))
(R/'delivery.json').write_text(json.dumps(dict(session_id='01a0892e-2964-7ec3-bd76-9ab4937980cb',
    exclusions='vendor separately covered by source-manifest and official source archive; regenerable build intermediates excluded; index excludes itself',files=rows),ensure_ascii=False,indent=2),encoding='utf8')
print('source_files',len(sources),'delivery_files',len(rows))
