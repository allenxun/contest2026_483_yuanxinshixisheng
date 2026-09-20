import pathlib,hashlib,json,subprocess,shutil
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]
source=P/'app/k7radio/prov_service.inc'
data=source.read_bytes()
(R/'input/prov_service.inc').write_bytes(data)
(R/'inputs.json').write_text(json.dumps({'source':str(source),'sha256':hashlib.sha256(data).hexdigest()},indent=2))
with (R/'test-output.txt').open('wb') as out:
 for opt in ['-O0','-O2']:
  exe='test'+opt[1:]+'.exe'
  for cmd in [[shutil.which('gcc'),'-std=c11',opt,'-Wall','-Wextra','-Werror','-pedantic','scan_collector.c','test.c','-o',exe],[str(R/exe)]]:
   out.write(('COMMAND '+repr(cmd)+'\n').encode())
   p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
   out.write(p.stdout);out.write(('EXIT %d\n'%p.returncode).encode())
   if p.returncode: raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
