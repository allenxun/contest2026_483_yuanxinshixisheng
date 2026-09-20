import pathlib,json,hashlib
R=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pdf=R/'es8388-user-guide-radxa.pdf'
assert sha(pdf)=='6d25413e840d096186b21f9aa1eff8b58b95ea97d216a248c60ea178884d0457'
(R/'acquired-source.json').write_text(json.dumps({'url':'https://dl.radxa.com/rock2/docs/hw/ds/ES8388%20user%20Guide.pdf','publisher_on_document':'Everest Semiconductor','host':'Radxa third-party mirror','title':'ES8388 User Guide','document_date':'2011-06-17','pages':28,'bytes':pdf.stat().st_size,'sha256':sha(pdf),'method':'urllib.request.urlopen(url,timeout=15).read(5242881); assert PDF and <=5MiB','hardware_review_status':'NOT_READY'},indent=2)+'\n')
files=[{'path':p.relative_to(R).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json']
(R/'delivery.json').write_text(json.dumps({'scope':'Public ES8388 document recovery and gap mapping, no hardware review promotion','files':files},indent=2)+'\n')
for e in files:assert sha(R/e['path'])==e['sha256']
print(sha(R/'delivery.json'))
