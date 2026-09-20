import pathlib,subprocess,json,hashlib
r=pathlib.Path(__file__).resolve().parent;results=[]
for opt in ['-O0','-O2']:
 exe='test'+opt+'.exe'
 for cmd,t in [([r'D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11',opt,'-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','playback_filter.c','test_filter.c','-lm','-o',exe],30),([str(r/exe)],15)]:
  p=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=t)
  results.append(dict(command=cmd,timeout_seconds=t,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));(r/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(p.stdout,p.stderr,end='')
  if p.returncode:raise SystemExit(p.returncode)
(r/'delivery.json').write_text(json.dumps([dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(r.iterdir()) if p.is_file() and p.name!='delivery.json'],indent=2),encoding='utf-8')
print('delivery',hashlib.sha256((r/'delivery.json').read_bytes()).hexdigest())
