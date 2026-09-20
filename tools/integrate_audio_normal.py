"""Integrate separately reviewed codec power and optional buffer playback."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
B=R/'work-in-progress/parallel-model-reader-medium/audio-codec-normal-power-v1'
manifest=json.loads((B/'delivery.json').read_text())
for f in manifest['files']: assert sha(B/f['path'])==f['sha256'],f['path']
assert sha(R/'app/k7sound/codec_duplex.c')=='6c5912ab7cd45f24bf9a8f410b1cc5a09071ab9dddd9725e231c2b7351218fb6'
assert sha(B/'codec_duplex.c')=='82906169d9285611ce9b2de0361347cc518cfba0620de78cd8b63ca86e9c0bee'
C=R/'work-in-progress/parallel-neon-probe-medium/audio-sai1-buffer-play-v1'
m=json.loads((C/'outputs.json').read_text())
for rel,digest in m.items():assert sha(C/rel)==digest,rel
assert sha(R/'app/k7sound/pio.c')=='e7608d58a48e852203be00d5316f7b9cabeae74ae5df927fdbefeb7cfa725458'
assert sha(R/'app/k7sound/pio.h')=='009c2bef0ad5166a52ba349d15a7c2a6cde04cd8147542688825ba5bf27d1560'
(R/'app/k7sound/codec_duplex.c').write_bytes((B/'codec_duplex.c').read_bytes())
for name in ('pio.c','pio.h'):(R/'app/k7sound'/name).write_bytes((C/name).read_bytes())
E=R/'evidence/audio-normal-20260910';E.mkdir(exist_ok=True)
(E/'candidate-review.json').write_text(json.dumps(dict(codec=manifest,pio=m,hardware_tested=False),indent=2))
print('Normal power adopted; optional raw buffer playback has no capture/tone path changes')
