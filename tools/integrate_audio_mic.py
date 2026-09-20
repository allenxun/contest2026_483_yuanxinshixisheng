"""Merge disjoint reviewed pad, external-clock and ADC diagnostic candidates."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/audio-mic-20260910';E.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
A=R/'work-in-progress/parallel-cxx-unwind-medium/audio-pad-clock-observe-v1'
B=R/'work-in-progress/parallel-model-reader-medium/audio-codec-adc-modes-v1'
C=R/'work-in-progress/parallel-neon-probe-medium/audio-mclkout-review-v1'
for directory in [A,B]:
    m=json.loads((directory/'delivery.json').read_text())
    for x in (m if isinstance(m,list) else m['files']):assert sha(directory/x['path'])==x['sha256'],x['path']
for rel,digest in json.loads((C/'outputs.json').read_text()).items():assert sha(C/rel)==digest,rel
for name in ['platform.c','platform.h']:
    assert sha(R/'app/k7sound'/name)==sha(A/('frozen-'+name))
    s=(C/name).read_text().replace('[9]','[10]').replace('i<9','i<10')
    if name.endswith('.c'):
        for before,after in [('IOC+0x4088};','IOC+0x4088,IOC+0x6144};'),
          ('0xf0f0,0xf000};','0xf0f0,0xf000,0xc0};'),('0x1010,0x1000};','0x1010,0x1000,0};')]:
            assert s.count(before)==1;s=s.replace(before,after)
    (R/'app/k7sound'/name).write_text(s,encoding='utf-8',newline='\n')
for name in ['codec_duplex.c','codec_duplex.h']:
    assert sha(R/'app/k7sound'/name)==sha(B/('input-'+name))
    (R/'app/k7sound'/name).write_bytes((B/name).read_bytes())
for name in ['observe.c','observe.h']:(R/'app/k7sound'/name).write_bytes((A/name).read_bytes())
(E/'candidate-review.json').write_text(json.dumps(dict(deliveries={p.relative_to(R).as_posix():sha(p) for p in [A/'delivery.json',B/'delivery.json',C/'outputs.json']},
 source={p.relative_to(R).as_posix():sha(p) for p in (R/'app/k7sound').rglob('*') if p.is_file()},hardware_passed=False),indent=2))
print('Merged independent 10-field pad state and separate MCLKOUT gate state')
