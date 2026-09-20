import pathlib,hashlib,json,subprocess,shutil,difflib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'app/k7sound'/n for n in ['pio.c','pio.h','input/rockchip_sai.h']]
paths += [P/'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip'/n for n in ['rockchip_sai.c','rockchip_sai.h']]
manifest=[]
for i,p in enumerate(paths):
 data=p.read_bytes();dest=R/'input'/('%02d_'%i+p.name)
 if dest.exists() and dest.read_bytes()!=data: raise SystemExit('Frozen input changed; do not overwrite '+str(dest))
 dest.write_bytes(data)
 manifest.append({'source':str(p),'sha256':hashlib.sha256(data).hexdigest(),'snapshot':dest.name})
(R/'inputs.json').write_text(json.dumps(manifest,indent=2))
patch=''
for i,n in enumerate(['pio.c','pio.h']):
 old=(R/'input'/('%02d_'%i+n)).read_text().splitlines(True);new=(R/n).read_text().splitlines(True)
 patch+=''.join(difflib.unified_diff(old,new,fromfile='a/app/k7sound/'+n,tofile='b/app/k7sound/'+n))
(R/'fifo-sum4.patch').write_text(patch)
with (R/'test-output.txt').open('wb') as f:
 for opt in ['-O0','-O2']:
  exe='test'+opt[1:]+'.exe'
  for cmd in [[shutil.which('gcc'),'-std=c11',opt,'-Wall','-Wextra','-Werror','-pedantic','pio.c','test.c','-o',exe],[str(R/exe)]]:
   f.write(('COMMAND '+repr(cmd)+'\n').encode());p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
   f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
   if p.returncode: print(p.stdout.decode());raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
