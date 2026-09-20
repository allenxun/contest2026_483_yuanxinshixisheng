"""Integrate frozen explicit RX2 readiness diagnostic only."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-neon-probe-medium/audio-rx2-guard-v1'
want='23908e20a22341ffaf8e559de6ba1e1d1581ca2af9564352cdfc17a19932c49e'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()==want
for row in json.loads((C/'outputs.json').read_text()):
 assert hashlib.sha256((C/row.get('path',row.get('name'))).read_bytes()).hexdigest()==row['sha256']
for row in json.loads((C/'inputs.json').read_text()):
 assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256']
for name in ('duplex.c','duplex.h','rx2_ready.c'):(R/'app/k7sound'/name).write_bytes((C/'candidate'/name).read_bytes())
p=R/'app/k7sound/k7sound_main.c';s=p.read_text()
mark='  bool rx2 = !strcmp(argv[1], "loopback-rx2");';assert mark in s
s=s.replace(mark,'  bool guarded = !strcmp(argv[1], "loopback-guard");\n  bool rx2 = guarded || !strcmp(argv[1], "loopback-rx2");')
s=s.replace('      if (rx2)\n','      if (guarded)\n        rc = dl_run_numbered_rx2_guard(&dl, platform.ready, 1, 4096000, loop_capture, 512, &loop_result);\n      else if (rx2)\n')
p.write_text(s,newline='\n')
p=R/'app/k7sound/CMakeLists.txt';s=p.read_text();a=s.index('SRCS ')+5;b=s.index('\n',a)
names=s[a:b].split();names=list(dict.fromkeys(names));names.append('rx2_ready.c')
s=s[:a]+' '.join(names)+s[b:];p.write_text(s,newline='\n')
p=R/'tools/sync_sdk.py';s=p.read_text();assert "'audio-mmu-20260910')" in s
s=s.replace("'audio-mmu-20260910')","'audio-mmu-20260910', 'audio-rx2-20260910')");p.write_text(s,newline='\n')
p=R/'tools/observe_audio_io.py';s=p.read_text()
s=s.replace("'audio-rx2-20260910'],","'audio-rx2-20260910','audio-guard-20260910'],")
s=s.replace("'k7sound loopback-rx2'],","'k7sound loopback-rx2','k7sound loopback-guard'],")
s=s.replace("'audio-rx2-20260910':'verify_audio_rx2_image'}","'audio-rx2-20260910':'verify_audio_rx2_image','audio-guard-20260910':'verify_audio_guard_image'}")
p.write_text(s,newline='\n')
E=R/'evidence/audio-guard-20260910';E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256=want,change='Explicit guarded RX2 pair-ready only',cmake='Add rx2_ready; remove duplicate MMU source entries',hardware_tested=False),indent=2))
print('Guard candidate integrated')
