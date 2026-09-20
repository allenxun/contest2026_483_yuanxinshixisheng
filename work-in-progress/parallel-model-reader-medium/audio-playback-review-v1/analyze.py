"""Read frozen UART dump, calculate digital levels; no audio or ASR execution."""
import hashlib, json, math, pathlib, re
ROOT=pathlib.Path('E:/openvela/VelaVision')
OUT=pathlib.Path(__file__).resolve().parent
paths=[f'evidence/audio-reset-20260910/k7sound-{x}.{ext}' for x in ('capture-48000-20260910-200557','replay-20260910-200608','dump-20260910-200625') for ext in ('bin','json')]
paths += ['app/k7sound/codec_duplex.c','app/k7sound/codec_duplex.h','app/k7sound/pio.c','app/k7sound/k7sound_main.c','work-in-progress/parallel-k7-audio/HARDWARE.md','work-in-progress/parallel-k7-audio/sources/K7_V2.0_20250716_SCH-p33.txt','work-in-progress/parallel-k7-audio/evidence/K7_V2.0_20250716_SCH-p33.png','work-in-progress/parallel-k7-audio/sources/K7_V2.0_20250716_SCH-p32.txt']
rows=[]
for rel in paths:
    p=ROOT/rel; data=p.read_bytes()
    rows.append(dict(path=rel,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    if rel.startswith('app/'):
        (OUT/('input-'+p.name)).write_bytes(data)
(OUT/'inputs.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
p=ROOT/'evidence/audio-reset-20260910/k7sound-dump-20260910-200625.bin'
words=[]
for line in p.read_bytes().decode('ascii',errors='replace').splitlines():
    m=re.fullmatch(r'PCM ([0-9a-f]{6})((?: [0-9a-f]{8})+)',line.strip())
    if m:
        assert int(m[1],16)==len(words), 'discontinuous dump index'
        words += [int(v,16) for v in m[2].split()]
assert len(words)==96000
signed=[v if v<2**31 else v-2**32 for v in words]
channels=[signed[0::2],signed[1::2]]
def db(v):return 20*math.log10(v/2**31) if v else None
def stats(x):
    peak=max(map(abs,x)); rms=math.sqrt(sum(v*v for v in x)/len(x))
    return dict(peak=peak,rms=rms,peak_dbfs=db(peak),rms_dbfs=db(rms),nonzero=sum(v!=0 for v in x),peak_after_codec_db=db(peak)-39,rms_after_codec_db=db(rms)-39)
avg=[(a+b)/2 for a,b in zip(*channels)]
report=dict(frames=48000,rate_declared=16000,duration_declared_seconds=3,channels=[stats(x) for x in channels],arithmetic_stereo_mean=stats(avg),frame_nonzero_by_mod4=[sum(channels[0][i]!=0 or channels[1][i]!=0 for i in range(k,48000,4)) for k in range(4)],interpretation='Digital-only arithmetic, no DAC volts or amplifier gain/SPL measurement. Full buffer retained, no zero removal.')
(OUT/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
