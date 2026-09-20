import pathlib,subprocess,json,hashlib,difflib
r=pathlib.Path(__file__).resolve().parent
results=[]
for opt in ['-O0','-O2']:
 cmd=[r'D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11',opt,'-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','pio.c','test_request.c','-o','test'+opt+'.exe']
 for command,limit in [(cmd,30),([str(r/('test'+opt+'.exe'))],15)]:
  p=subprocess.run(command,cwd=r,capture_output=True,text=True,timeout=limit)
  results.append(dict(command=command,timeout_seconds=limit,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
  (r/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  print(p.stdout,p.stderr,end='')
  if p.returncode:raise SystemExit(p.returncode)
# Original C, including entry points, is an exact byte prefix.
assert (r/'pio.c').read_bytes().startswith((r/'input-pio.c').read_bytes())
patch=''
for name in ['pio.c','pio.h']:
 patch+=''.join(difflib.unified_diff((r/('input-'+name)).read_text().splitlines(True),(r/name).read_text().splitlines(True),fromfile='a/app/k7sound/'+name,tofile='b/app/k7sound/'+name))
(r/'request.patch').write_text(patch,encoding='utf-8')
(r/'delivery.json').write_text(json.dumps([dict(path=p.relative_to(r).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(r.rglob('*')) if p.is_file() and p.name!='delivery.json'],indent=2),encoding='utf-8')
print('delivery',hashlib.sha256((r/'delivery.json').read_bytes()).hexdigest())
