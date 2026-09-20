import pathlib,subprocess,json,hashlib
R=pathlib.Path(__file__).resolve().parent; P=R.parents[2]; K=P/'work-in-progress/parallel-k7-codec'
paths=[K/'include/codec_txn.h',K/'src/codec_txn.c',K/'input/kernel-6.1/sound/soc/codecs/es8323.c',K/'input/kernel-6.1/sound/soc/codecs/es8323.h',K/'input/kernel-6.1/arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi',P/'work-in-progress/parallel-model-reader-medium/audio-codec-plan-v1/HANDOFF.md',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/HANDOFF.md',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf',P/'evidence/audio-sdk-extra-20260910/inputs.json']
(R/'inputs.json').write_text(json.dumps([{'path':p.relative_to(P).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],indent=2)+'\n')
gcc=r'D:\software\mingw64\mingw64\bin\gcc.exe';results=[]
for cmd,timeout in [([gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','-I'+str(K/'include'),str(K/'src/codec_txn.c'),'capture_reference.c','test_reference.c','-o','test_reference.exe'],30),([str(R/'test_reference.exe')],15)]:
 r=subprocess.run(cmd,cwd=R,capture_output=True,text=True,timeout=timeout)
 results.append(dict(command=cmd,timeout_seconds=timeout,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
 (R/'results.json').write_text(json.dumps(results,indent=2)+'\n'); print(r.stdout,r.stderr,end='');assert r.returncode==0
