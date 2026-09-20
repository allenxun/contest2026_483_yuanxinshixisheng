import pathlib,json,hashlib
R=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files=[{'path':p.relative_to(R).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json']
(R/'delivery.json').write_text(json.dumps({'scope':'FAT reader contract audit; selected real functions, mocked ABI/environment; no USB or target execution','files':files},indent=2)+'\n')
for e in files:assert sha(R/e['path'])==e['sha256']
print('delivery.json SHA256',sha(R/'delivery.json'))
