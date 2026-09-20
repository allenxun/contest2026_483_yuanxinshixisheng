"""Summarize preserved loopback words; do not remove zero samples."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

p = argparse.ArgumentParser()
p.add_argument('raw', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
data = a.raw.read_bytes()
text = data.decode('ascii', errors='replace')
summary = re.search(r'SOUND loopback result=(-?\d+) frames=(\d+) tx_queued=(\d+) polls=(\d+) stop=(-?\d+) restore=(-?\d+) amp=(-?\d+) held=(\d+)', text)
if not summary:
    raise SystemExit('No loopback result in raw evidence')
values = list(map(int, summary.groups()))
words = []
for line in text.splitlines():
    m = re.fullmatch(r'LOOP_PCM ([0-9a-f]{4})((?: [0-9a-f]{8})+)', line.strip())
    if m:
        if int(m[1], 16) != len(words):
            raise SystemExit('Noncontiguous raw sample offsets')
        words.extend(int(x, 16) for x in m[2].split())
if len(words) != values[1] * 2:
    raise SystemExit('Missing or extra raw samples')
paths = re.search(r'SOUND loop_path before=([0-9a-f]+) active=([0-9a-f]+) restored=([0-9a-f]+) start=(\d+) end=(\d+)', text)
if not paths:
    raise SystemExit('Missing route snapshot')
report = dict(raw=str(a.raw.resolve()), sha256=hashlib.sha256(data).hexdigest(),
    result=values[0], frames=values[1], tx_enqueued=values[2],
    stop=values[4], restore=values[5], amp=values[6], held=values[7],
    path_before=paths[1], path_active=paths[2], path_restored=paths[3],
    duration_us=int(paths[5])-int(paths[4]),
    nonzero_by_channel_phase=[[sum(words[2*i+c] != 0 for i in range(phase,values[1],4)) for phase in range(4)] for c in range(2)],
    zero_word_count=words.count(0), unique_word_count=len(set(words)),
    eight_word_groups=[dict(words=['%08x'%v for v in k], count=n) for k,n in Counter(tuple(words[i:i+8]) for i in range(0,len(words),8)).most_common()],
    words_preserved=True, audio_quality_accepted=False,
    note='Counts describe raw transport only, not sample rate, fresh marker identity or acoustic quality.')
if a.output.exists():
    raise SystemExit('Refusing to overwrite analysis')
a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
