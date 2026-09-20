"""Copy reviewed independent candidates into disabled formal components."""
import hashlib
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
out=R/'evidence/agent-prerequisites-20260910'
out.mkdir(exist_ok=True)
assert not (out/'integration.json').exists()
records=[]
def copy(source,target,transform=None):
    a=R/source; b=R/target
    assert not b.exists(),str(b)
    raw=a.read_bytes()
    b.parent.mkdir(parents=True,exist_ok=True)
    if transform: b.write_text(transform(raw.decode()),newline='\n')
    else: b.write_bytes(raw)
    records.append(dict(source=source,target=target,
                        source_sha256=hashlib.sha256(raw).hexdigest(),
                        target_sha256=hashlib.sha256(b.read_bytes()).hexdigest()))
copy('work-in-progress/parallel-model-reader-medium/model_reader.c','app/k7agent/model_reader/model_reader.c')
copy('work-in-progress/parallel-model-reader-medium/model_reader.h','app/k7agent/model_reader/model_reader.h')
copy('work-in-progress/parallel-neon-probe-medium/probe_main.c','app/k7neon/k7neon_main.c',lambda s:s.replace('int main(int argc, char **argv)','int k7neon_main(int argc, char **argv)'))
for n in ['probe.h','neon_hold.S']:
    copy('work-in-progress/parallel-neon-probe-medium/'+n,'app/k7neon/'+n)
(out/'integration.json').write_text(json.dumps(dict(files=records,enabled_in_running_firmware=False,
    note='Reader POSIX backend remains disabled pending verified regular-file mount. NEON pending cross-compile and board test.'),indent=2)+'\n')
print('Integrated source candidates; no running firmware change')
