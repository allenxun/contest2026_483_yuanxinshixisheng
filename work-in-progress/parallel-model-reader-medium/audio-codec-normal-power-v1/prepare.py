import pathlib,hashlib,json,difflib
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
paths=[P/'app/k7sound/codec_duplex.c',P/'app/k7sound/codec_duplex.h',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.c',P/'work-in-progress/parallel-k7-codec/input/kernel-6.1/sound/soc/codecs/es8323.h',P/'work-in-progress/parallel-model-reader-medium/audio-codec-datasheet-v1/es8388-user-guide-radxa.pdf']
entries=[]
for p in paths:
 b=p.read_bytes();entries.append(dict(path=p.relative_to(P).as_posix(),sha256=hashlib.sha256(b).hexdigest()))
 if p.parent.name=='k7sound':
  (R/('input-'+p.name)).write_bytes(b);(R/p.name).write_bytes(b)
s=(R/'codec_duplex.c').read_text()
old=' {0x06,0xc3,0,0},{0x19,0x06,0x04,0},{0x0f,0x34,0x04,0},'
new=''' /* Normal-power comparison: Linux set_bias(STANDBY) register order.
  * Keep both ADCs enabled later (03=00), do not copy 03=59. */
 {0x07,0x7c,0x7f,0},{0x05,0x00,0xe8,0},{0x06,0x00,0xc3,0},
 {0x19,0x06,0x04,0},{0x0f,0x34,0x04,0},'''
assert s.count(old)==1
t=s.replace(old,new);(R/'codec_duplex.c').write_text(t)
(R/'normal-power.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),t.splitlines(True),fromfile='a/codec_duplex.c',tofile='b/codec_duplex.c')))
v2=P/'work-in-progress/parallel-model-reader-medium/audio-codec-duplex-v2'
for name in ['test_duplex.c','run_tests.py','seal_delivery.py']:(R/name).write_bytes((v2/name).read_bytes())
test=(R/'test_duplex.c').read_text().replace('prepare_calls=m.calls;','prepare_calls=m.calls;\n  ck(m.regs[5]==0 && m.regs[6]==0 && m.regs[7]==0x7c && m.regs[3]==0);')
(R/'test_duplex.c').write_text(test)
(R/'frozen-inputs.json').write_text(json.dumps(entries,indent=2)+'\n')
print('candidate',hashlib.sha256((R/'codec_duplex.c').read_bytes()).hexdigest())
