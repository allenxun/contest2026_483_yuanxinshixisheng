import pathlib,hashlib,json,subprocess,shutil,difflib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
B=P/'work-in-progress/parallel-k7-audio/sources/kernel-6.1'
paths=[B/'arch/arm64/boot/dts/rockchip'/n for n in ['rk3576.dtsi','rk3576-kickpi-k7.dtsi']]
paths += [B/'sound/soc/codecs/es8323.c',P/'evidence/audio-sdk-extra-20260910/kernel-6.1/drivers/clk/rockchip/clk-rk3576.c']
paths += [p for p in (P/'evidence/audio-clkout-reference-20260910').rglob('*') if p.is_file()]
manifest=[]
for i,p in enumerate(paths):
 data=p.read_bytes();d=R/'input'/('%02d_'%i+p.name);d.write_bytes(data)
 manifest.append({'source':str(p),'sha256':hashlib.sha256(data).hexdigest(),'snapshot':d.name})
for n in ['platform.c','platform.h']:
 manifest.append({'source':'app/k7sound/'+n,'sha256':hashlib.sha256((R/'input'/n).read_bytes()).hexdigest(),'snapshot':n})
(R/'inputs.json').write_text(json.dumps(manifest,indent=2))
patch=''
for n in ['platform.c','platform.h']:
 patch+=''.join(difflib.unified_diff((R/'input'/n).read_text().splitlines(True),(R/n).read_text().splitlines(True),fromfile='a/app/k7sound/'+n,tofile='b/app/k7sound/'+n))
(R/'mclkout.patch').write_text(patch)
with (R/'test-output.txt').open('wb') as f:
 for opt in ['-O0','-O2']:
  exe='test'+opt[1:]+'.exe'
  for cmd in [[shutil.which('gcc'),'-std=c11',opt,'-Wall','-Wextra','-Werror','-pedantic','platform.c','test_platform.c','-o',exe],[str(R/exe)]]:
   f.write(('COMMAND '+repr(cmd)+'\n').encode());p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
   f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
   if p.returncode:print(p.stdout.decode());raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
