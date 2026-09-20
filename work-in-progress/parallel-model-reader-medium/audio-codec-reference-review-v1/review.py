import pathlib,json,hashlib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'app/k7sound/codec_duplex.c',P/'app/k7sound/codec_duplex.h',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.c',P/'work-in-progress/parallel-k7-audio/HARDWARE.md']
entries=[]
for p in paths:
 b=p.read_bytes();entries.append(dict(path=p.relative_to(P).as_posix(),sha256=hashlib.sha256(b).hexdigest()))
 if p.parent.name=='k7sound':(R/('input-'+p.name)).write_bytes(b)
(R/'inputs.json').write_text(json.dumps(entries,indent=2)+'\n')
assert 0x00&0xaa==0x55&0xaa==0
assert 0x36&4==0x05&4==4
assert (0x60^0x40)==0x20
assert (0x36^0x35)==3 and (0x36&0xfc)==(0x35&0xfc)
(R/'decode-checks.json').write_text(json.dumps({'scope':'Bit arithmetic only, not hardware verification','adc_control_mask':170,'dac_control_mask':85,'current02_adc_bits':0,'guide02_adc_bits':0,'current00_reference_enabled':True,'guide00_reference_enabled':True,'reg01_difference':32,'all_assertions_passed':True},indent=2)+'\n')
files=[dict(path=p.relative_to(R).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='delivery.json']
(R/'delivery.json').write_text(json.dumps({'scope':'Read-only reference power/clock comparison; no patch/device','files':files},indent=2)+'\n')
print(hashlib.sha256((R/'delivery.json').read_bytes()).hexdigest())
