from pathlib import Path
import hashlib,json
r=Path('E:/openvela/VelaVision');p=r/'work-in-progress/parallel-model-reader-medium/audio-pio-contract-v1';(p/'input').mkdir(exist_ok=True)
paths=['evidence/audio-sai-trm-20260910/SAI-layout.txt','evidence/audio-sai-trm-20260910/input.json','work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c','app/k7sound/input/rockchip_sai.h','app/k7sound/pio.c']
a=[]
for i,n in enumerate(paths):
 b=(r/n).read_bytes();q=f'input/{i:02d}-'+Path(n).name;(p/q).write_bytes(b);a.append({'path':n,'snapshot':q,'sha256':hashlib.sha256(b).hexdigest()})
(p/'inputs.json').write_text(json.dumps(a,indent=2))
