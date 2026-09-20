import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'app/k7sound'/n for n in ['pio.c','pio.h','k7sound_main.c','i2c_owner.inc','input/rockchip_sai.h']]
paths += [P/'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip'/n for n in ['rockchip_sai.c','rockchip_sai.h']]
paths += [P/'evidence/audio-mic-20260910'/n for n in ['k7sound-capture-20260910-192011.bin','k7sound-capture-48000-20260910-192109.bin']]
records=[]
for i,p in enumerate(paths):
 data=p.read_bytes();d=R/'input'/('%02d_'%i+p.name);d.write_bytes(data)
 records.append({'source':str(p),'snapshot':d.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'source-inputs.json').write_text(json.dumps(records,indent=2))
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
