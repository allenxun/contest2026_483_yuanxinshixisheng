import pathlib,hashlib,json,subprocess,shutil,difflib
R=pathlib.Path(__file__).resolve().parent
records=[{'source':'app/k7sound/'+n,'snapshot':'input/'+n,'sha256':hashlib.sha256((R/'input'/n).read_bytes()).hexdigest()} for n in ['pio.c','pio.h']]
(R/'inputs.json').write_text(json.dumps(records,indent=2))
patch=''
for n in ['pio.c','pio.h']:
 patch+=''.join(difflib.unified_diff((R/'input'/n).read_text().splitlines(True),(R/n).read_text().splitlines(True),fromfile='a/app/k7sound/'+n,tofile='b/app/k7sound/'+n))
(R/'rx-trace.patch').write_text(patch)
with (R/'test-output.txt').open('wb') as f:
 for opt in ['-O0','-O2']:
  exe='test'+opt[1:]+'.exe'
  for cmd in [[shutil.which('gcc'),'-std=c11',opt,'-Wall','-Wextra','-Werror','-pedantic','pio.c','test.c','-o',exe],[str(R/exe)]]:
   f.write(('COMMAND '+repr(cmd)+'\n').encode());p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
   f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
   if p.returncode:print(p.stdout.decode());raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
