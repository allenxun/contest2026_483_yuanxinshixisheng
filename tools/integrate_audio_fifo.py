"""Adopt the reviewed four-field FIFO fix with frozen-input verification."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-neon-probe-medium/audio-sai1-pio-v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((C/'outputs.json').read_text())
for rel,digest in m.items(): assert sha(C/rel)==digest,rel
for name,index in [('pio.c','00'),('pio.h','01')]:
    assert sha(R/'app/k7sound'/name)==sha(C/'input'/(index+'_'+name))
    (R/'app/k7sound'/name).write_bytes((C/name).read_bytes())
p=R/'app/k7sound/k7sound_main.c';s=p.read_text()
needle='rc, result.frames, result.polls, result.stop_result, result.held, result.max_fifo);'
assert s.count(needle)==1
s=s.replace(needle,needle+'\n      printf("SOUND fifo first=%08" PRIx32 " last=%08" PRIx32 " TXCR=%08" PRIx32 " RXCR=%08" PRIx32 " FSCR=%08" PRIx32 " CKR=%08" PRIx32 "\\n",\n             result.first_fifo_raw, result.last_fifo_raw, rd(NULL, SAI + SAI_TXCR),\n             rd(NULL, SAI + SAI_RXCR), rd(NULL, SAI + SAI_FSCR), rd(NULL, SAI + SAI_CKR));')
p.write_text(s,encoding='utf-8',newline='\n')
E=R/'evidence/audio-fifo-20260910';E.mkdir(exist_ok=True)
(E/'candidate-review.json').write_text(json.dumps(dict(candidate=C.relative_to(R).as_posix(),
 verified_outputs=m,host_results=(C/'test-output.txt').read_text(),hardware_passed=False,
 formal={p.relative_to(R).as_posix():sha(p) for p in (R/'app/k7sound').rglob('*') if p.is_file()}),indent=2))
print('Adopted exact PIO candidate plus root raw-register diagnostic')
