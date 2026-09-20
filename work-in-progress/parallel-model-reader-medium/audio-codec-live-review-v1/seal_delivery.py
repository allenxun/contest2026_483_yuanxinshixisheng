import pathlib,json,hashlib
R=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[dict(path=p.relative_to(R).as_posix(),sha256=sha(p)) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json']
(R/'delivery.json').write_text(json.dumps({'scope':'Read-only live codec32/route review; no hardware/patch','files':files},indent=2)+'\n')
for e in files:assert sha(R/e['path'])==e['sha256']
print(sha(R/'delivery.json'))
