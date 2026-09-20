import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'app/k7sound'/n for n in ['pio.c','pio.h','platform.c','platform.h','input/rockchip_sai.h']]
B=P/'work-in-progress/parallel-k7-audio/sources/kernel-6.1'
paths += [B/'sound/soc/rockchip'/n for n in ['rockchip_sai.c','rockchip_sai.h']]
paths += [B/'arch/arm64/boot/dts/rockchip'/n for n in ['rk3576.dtsi','rk3576-kickpi-k7.dtsi']]
records=[]
for i,p in enumerate(paths):
 if not p.exists():continue
 data=p.read_bytes();d=R/'input'/('%02d_'%i+p.name)
 if d.exists() and d.read_bytes()!=data:raise SystemExit('frozen input changed')
 d.write_bytes(data);records.append({'source':str(p),'snapshot':d.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(records,indent=2))
rx=0x00400fff;fs=0x0101f03f;ck=0x18
decoded={'vdw':(rx&31)+1,'slot_width':((rx>>5)&31)+1,'slots':((rx>>11)&127)+1,'lanes':((rx>>20)&3)+1,'edge_shift':(rx>>22)&1,'standalone':not bool(rx&(1<<23)),'frame_bclks':(fs&4095)+1,'pulse_bclks':((fs>>12)&4095)+1,'mclk_div':((ck>>3)&4095)+1,'slave_bit':bool(ck&4)}
assert decoded['vdw']==32 and decoded['slot_width']==32 and decoded['slots']==2 and decoded['lanes']==1
assert decoded['frame_bclks']==64 and decoded['pulse_bclks']==32 and decoded['mclk_div']==4
(R/'register-decode.json').write_text(json.dumps(decoded,indent=2))
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2))
print('Frozen sources; reported register arithmetic verified only. No hardware run.')
