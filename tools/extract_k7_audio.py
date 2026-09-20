"""Decode a complete, contiguous K7 RAM capture dump into unnormalised WAVs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import wave

p = argparse.ArgumentParser()
p.add_argument('dump', type=Path)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
raw = a.dump.read_bytes()
headers = re.findall(rb'^SOUND_PCM frames=(\d+) rate=16000 channels=2 bits=32\r*$', raw, re.M)
assert len(headers) == 1 and raw.count(b'SOUND_PCM_END') == 1, 'Incomplete/ambiguous capture'
frames = int(headers[0])
assert 0 < frames <= 48000
values = []
for row in re.findall(rb'^PCM ([0-9a-f]{6})((?: [0-9a-f]{8})+)\r*$', raw, re.M):
    assert int(row[0], 16) == len(values), 'Missing/duplicate/out-of-order sample rows'
    fields = row[1].split()
    assert 1 <= len(fields) <= 8
    values.extend(int(v, 16) for v in fields)
assert len(values) == 2 * frames, 'Sample count mismatch'
pcm32 = b''.join(struct.pack('<I', v) for v in values)
signed = [v if v < 0x80000000 else v-0x100000000 for v in values]
pcm16 = b''.join(struct.pack('<h', v >> 16) for v in signed)
a.out.mkdir(parents=True, exist_ok=False)
outputs = {}
for name, width, data in [('capture-raw32.wav',4,pcm32),('capture-high16.wav',2,pcm16)]:
    path = a.out/name
    with wave.open(str(path),'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(width)
        w.setframerate(16000)
        w.writeframes(data)
    outputs[name] = hashlib.sha256(path.read_bytes()).hexdigest()
report = dict(input=str(a.dump.resolve()), input_sha256=hashlib.sha256(raw).hexdigest(),
              frames=frames, seconds=frames/16000, rate=16000, channels=2,
              conversion='No gain/normalization; high16 is arithmetic right shift of raw signed32',
              min=[min(signed[ch::2]) for ch in range(2)],
              max=[max(signed[ch::2]) for ch in range(2)],
              unique=[len(set(signed[ch::2])) for ch in range(2)],
              nonzero=[sum(v!=0 for v in signed[ch::2]) for ch in range(2)],
              acoustic_validation=False, outputs=outputs)
(a.out/'extraction.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
