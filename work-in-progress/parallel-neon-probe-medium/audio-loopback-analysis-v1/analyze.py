import pathlib,hashlib,json,re
p=pathlib.Path(__file__).resolve().parent
root=p.parents[2]
names=['evidence/audio-loopback-20260910/k7sound-loopback-20260910-212123.bin',
 'evidence/audio-sai-trm-20260910/SAI-layout.txt',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.h',
 'app/k7sound/duplex.c','app/k7sound/duplex.h']
manifest=[]
for n in names:
 b=(root/n).read_bytes();f=p/'input'/n;f.parent.mkdir(parents=True,exist_ok=True)
 if f.exists():assert f.read_bytes()==b
 else:f.write_bytes(b)
 manifest.append(dict(path=n,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(manifest,indent=2))
text=(p/'input'/names[0]).read_text(encoding='ascii')
words=[]
for off,body in re.findall(r'^LOOP_PCM ([0-9a-f]+) ([0-9a-f ]+)\r?$',text,re.M):
 assert int(off,16)==len(words)
 words += [int(v,16) for v in body.split()]
assert len(words)==256
assert words[:8]==[0]*8
assert words[8:]==[0x0707ef00,0x08081100,0,0,0,0,0,0]*31
records=[tuple(int(v,16 if j in (3,4,5) else 10) for j,v in enumerate(x)) for x in re.findall(
 r'loop_word dir=(\d+) index=(\d+) us=(\d+) before=([0-9a-f]+) word=([0-9a-f]+) after=([0-9a-f]+) rc=0',text)]
tx=[x for x in records if x[0]==0];rx=[x for x in records if x[0]==1]
assert len(tx)==len(rx)==64
def levels(raw):return [(raw>>(6*i))&63 for i in range(4)]
prefill=[]
for x in tx[:16]:
 delta=[a-b for a,b in zip(levels(x[5]),levels(x[3]))]
 bank=x[1]//2%4
 assert delta==[int(i==bank) for i in range(4)]
 prefill.append(dict(index=x[1],bank=bank,word=hex(x[4])))
for x in rx:
 delta=[b-a for a,b in zip(levels(x[5]),levels(x[3]))]
 # Streaming arrivals may coincide with the read; preserve raw if so.
 assert sum(delta)==1
 assert x[4]==words[x[1]]
result=dict(frames=128,raw_words=256,initial_zero_words=8,
 nonzero_by_frame_mod4=[[sum(words[2*i+c]!=0 for i in range(phase,128,4)) for phase in range(4)] for c in range(2)],
 tx_prefill=prefill,rx_trace_words=len(rx),
 tx_prefill_total=levels(tx[15][5]),
 steady_pattern=['%08x'%x for x in words[8:16]],
 conclusion='Internal loopback reproduces sparse phases; codec ADC/external SDI not necessary. FIFO-bank to serial-path mapping unresolved.')
(p/'results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
print('PASS raw 256-word pattern and FIFO trace checks; no sample manipulation')
