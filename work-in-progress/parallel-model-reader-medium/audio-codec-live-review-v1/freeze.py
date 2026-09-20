import pathlib,json,hashlib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=list((P/'app/k7sound').rglob('*'))
paths+=[P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.c',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.h',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/arch/arm64/boot/dts/rockchip/rk3576-kickpi-k7.dtsi',P/'work-in-progress/parallel-neon-probe-medium/audio-sai1-pio-v1/input/00_rockchip_sai.c',P/'work-in-progress/parallel-k7-audio/HARDWARE.md',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf']
entries=[]
for p in paths:
 if not p.is_file():continue
 data=p.read_bytes();rel=p.relative_to(P)
 if str(rel).startswith('app'):
  dest=R/'snapshot'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 entries.append(dict(path=rel.as_posix(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
(R/'inputs.json').write_text(json.dumps(entries,indent=2)+'\n')
print('Frozen',len(entries),'inputs; only app snapshot copied, other sources hash-referenced')
