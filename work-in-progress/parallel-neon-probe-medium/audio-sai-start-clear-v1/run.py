import pathlib,hashlib,json,subprocess,shutil
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'evidence/audio-sai-trm-20260910'/n for n in ['SAI-application.txt','SAI-layout.txt','input.json']]
records=[]
for i,p in enumerate(paths):
 data=p.read_bytes();d=R/'input'/('%02d_'%i+p.name)
 if d.exists() and d.read_bytes()!=data:raise SystemExit('input changed')
 d.write_bytes(data);records.append({'source':str(p),'snapshot':d.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(records,indent=2))
with (R/'test-output.txt').open('wb') as f:
 for opt in ['-O0','-O2']:
  exe='test'+opt[1:]+'.exe'
  for cmd in [[shutil.which('gcc'),'-std=c11',opt,'-Wall','-Wextra','-Werror','-pedantic','start_clear.c','test.c','-o',exe],[str(R/exe)]]:
   f.write(('COMMAND '+repr(cmd)+'\n').encode());p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
   f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
   if p.returncode:print(p.stdout.decode());raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
