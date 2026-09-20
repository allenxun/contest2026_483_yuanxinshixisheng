"""Integrate fixed-target read-only MMU command, preserving all audio paths."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-neon-probe-medium/audio-mmu-integration-v1'
want='0ca68a9344737d1e8b30de21711c20a23781450079da9b166104d468d0ef8ab0'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()==want
for f in json.loads((C/'outputs.json').read_text()):
    assert hashlib.sha256((C/f.get('path',f.get('name'))).read_bytes()).hexdigest()==f['sha256']
for f in json.loads((C/'inputs.json').read_text()):
    assert hashlib.sha256((R/f['path']).read_bytes()).hexdigest()==f['sha256']
names=['mmu_command.c','mmu_command.h','command_core.c','command_core.h','mmu_probe.c','mmu_probe.h','snapshot_arm64.c']
for n in names:
    p=R/'app/k7sound'/n; assert not p.exists(); p.write_bytes((C/n).read_bytes())
p=R/'app/k7sound/k7sound_main.c'; s=p.read_text()
s=s.replace('#include "duplex.h"','#include "duplex.h"\n#include "mmu_command.h"')
old='int main(int argc, char **argv)\n{'
assert old in s
s=s.replace(old,old+'\n  if (argc > 1 && !strcmp(argv[1], "mmu"))\n    return k7sound_mmu_command(argc, argv, &owner);')
p.write_text(s,newline='\n')
p=R/'app/k7sound/CMakeLists.txt'; s=p.read_text()
s=s.replace('duplex.c','duplex.c mmu_command.c command_core.c mmu_probe.c snapshot_arm64.c')
p.write_text(s,newline='\n')
p=R/'tools/sync_sdk.py'; s=p.read_text()
assert "'audio-route-20260910')" in s
s=s.replace("'audio-route-20260910')","'audio-route-20260910', 'audio-marker-20260910')")
p.write_text(s,newline='\n')
E=R/'evidence/audio-mmu-20260910'; E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256=want,
    target_va='0x2a610000',cpu=0,readonly=True,hardware_tested=False,
    command_requires_exact_elf_binding=True),indent=2))
print('Read-only MMU command integrated; no audio register changes')
