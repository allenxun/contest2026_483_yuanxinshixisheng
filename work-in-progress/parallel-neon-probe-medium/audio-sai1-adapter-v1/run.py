import pathlib, subprocess, hashlib, json, shutil
R = pathlib.Path(__file__).resolve().parent
P = R.parents[2]
sources = [
 'docs/VoiceLink交接接收与集成顺序_20260910.md',
 'work-in-progress/parallel-k7-audio/HANDOFF.md',
 'work-in-progress/parallel-k7-codec/HANDOFF.md',
 'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c',
 'port/new/nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c',
 'port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.c',
 'port/new/nuttx/arch/arm64/include/rk3576/irq.h',
 'board/kickpi_k7/configs/velavision_usb_readonly_local/defconfig']
base='work-in-progress/parallel-k7-audio/sources/kernel-6.1/'
sources += [base+'sound/soc/rockchip/'+n for n in ['rockchip_sai.c','rockchip_sai.h','rockchip_i2s_tdm.h']]
sources += [base+'arch/arm64/boot/dts/rockchip/'+n for n in ['rk3576.dtsi','rk3576-kickpi-k7.dtsi']]
sources += [str(p.relative_to(P)).replace('\\','/') for p in (P/'evidence/audio-sdk-extra-20260910').rglob('*') if p.is_file()]
manifest=[]
for i,s in enumerate(sources):
 data=(P/s).read_bytes()
 dest=R/'input'/('%02d_'%i+(P/s).name)
 dest.write_bytes(data)
 manifest.append({'source':s,'snapshot':str(dest.relative_to(R)), 'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
compiler=shutil.which('gcc')
commands=[[compiler,'-std=c11','-Wall','-Wextra','-Werror','-pedantic','recipe.c','test.c','-o','test.exe'],[str(R/'test.exe')]]
with (R/'test-output.txt').open('wb') as f:
 for cmd in commands:
  f.write(('COMMAND '+repr(cmd)+'\n').encode('utf-8'))
  p=subprocess.run(cmd,cwd=str(R),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
  f.write(p.stdout); f.write(('EXIT %d\n'%p.returncode).encode())
  if p.returncode: raise SystemExit(p.returncode)
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print((R/'test-output.txt').read_text())
