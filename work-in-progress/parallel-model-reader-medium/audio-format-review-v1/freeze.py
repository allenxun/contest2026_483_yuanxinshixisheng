from pathlib import Path
import hashlib,json
r=Path('E:/openvela/VelaVision');p=r/'work-in-progress/parallel-model-reader-medium/audio-format-review-v1';(p/'input').mkdir(exist_ok=True)
paths=['app/k7sound/pio.c','app/k7sound/duplex.c','app/k7sound/k7sound_main.c','app/k7sound/codec_duplex.c','app/k7sound/input/rockchip_sai.h','evidence/audio-sai-trm-20260910/SAI-layout.txt','evidence/audio-sai-trm-20260910/input.json','work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c','work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/codecs/es8323.c','work-in-progress/parallel-k7-audio/sources/K7_V1.1_20241211_SCH-p32.txt','work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/guide-text.txt','work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/acquired-source.json']
v=[]
for i,n in enumerate(paths):
 b=(r/n).read_bytes(); name=f'{i:02d}-'+Path(n).name;(p/'input'/name).write_bytes(b);v.append({'path':n,'snapshot':'input/'+name,'sha256':hashlib.sha256(b).hexdigest()})
(p/'inputs.json').write_text(json.dumps(v,indent=2))
