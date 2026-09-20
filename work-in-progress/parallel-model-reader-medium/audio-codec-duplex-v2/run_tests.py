import pathlib,subprocess,json,hashlib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
results=[]
for opt in ['-O0','-O2']:
 for cmd,limit in [([r'D:\software\mingw64\mingw64\bin\gcc.exe','-std=c11',opt,'-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','codec_duplex.c','test_duplex.c','-o','test'+opt[1:]+'.exe'],30),([str(R/('test'+opt[1:]+'.exe'))],15)]:
  r=subprocess.run(cmd,cwd=R,capture_output=True,text=True,timeout=limit)
  results.append(dict(command=cmd,timeout_seconds=limit,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
  (R/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(r.stdout,r.stderr,end='')
  if r.returncode:raise SystemExit(r.returncode)
base=P/'work-in-progress/parallel-k7-codec/input/kernel-6.1'
paths=[base/'sound/soc/codecs/es8323.c',base/'sound/soc/codecs/es8323.h',base/'arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi',base/'sound/soc/rockchip/rockchip_multicodecs.c',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf',P/'work-in-progress/parallel-k7-audio/HARDWARE.md',P/'work-in-progress/parallel-k7-audio/sources/K7_V2.0_20250716_SCH-p32.txt',P/'work-in-progress/parallel-k7-audio/sources/K7_V2.0_20250716_SCH-p33.txt']
paths += [P/'work-in-progress/parallel-model-reader-medium/audio-codec-duplex-v1/codec_duplex.c',P/'work-in-progress/parallel-model-reader-medium/audio-codec-duplex-v1/codec_duplex.h',P/'work-in-progress/parallel-neon-probe-medium/audio-sai1-pio-v1/pio.c',P/'work-in-progress/parallel-neon-probe-medium/audio-sai1-pio-v1/pio.h']
(R/'inputs.json').write_text(json.dumps([dict(path=p.relative_to(P).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],indent=2)+'\n')
