import pathlib,subprocess,hashlib,json,shutil
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[]
b=P/'work-in-progress/parallel-k7-audio/sources/kernel-6.1'
paths += [b/'sound/soc/rockchip'/n for n in ['rockchip_sai.c','rockchip_sai.h']]
paths += [b/'arch/arm64/boot/dts/rockchip'/n for n in ['rk3576.dtsi','rk3576-pinctrl.dtsi','rk3576-kickpi-k7.dtsi']]
paths += [p for p in (P/'evidence/audio-sdk-extra-20260910').rglob('*') if p.is_file()]
paths += [p for p in (P/'evidence/audio-power-reference-20260910').rglob('*') if p.is_file()]
manifest=[]
for i,p in enumerate(paths):
 data=p.read_bytes();d=R/'input'/('%02d_'%i+p.name);d.write_bytes(data)
 manifest.append({'source':str(p),'snapshot':d.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(manifest,indent=2))
with (R/'test-output.txt').open('wb') as f:
 for cmd in [[shutil.which('gcc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','pio.c','test.c','-o','test.exe'],[str(R/'test.exe')],[shutil.which('gcc'),'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic','platform.c','test_platform.c','-o','test_platform.exe'],[str(R/'test_platform.exe')]]:
  f.write(('COMMAND '+repr(cmd)+'\n').encode());p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
  f.write(p.stdout);f.write(('EXIT %d\n'%p.returncode).encode())
  if p.returncode: print(p.stdout.decode());raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print((R/'test-output.txt').read_text())
