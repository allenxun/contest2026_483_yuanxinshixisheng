"""Integrate one explicit silent RX route experiment; default path preserved."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
C = R / 'work-in-progress/parallel-neon-probe-medium/audio-loopback-analysis-v1'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest() == 'c861e97a8436e954ba57c70ba0766c244be7d6e74185e7610627eb682f0eae8d'
for row in json.loads((C/'outputs.json').read_text()):
    assert hashlib.sha256((C/row.get('name',row.get('path'))).read_bytes()).hexdigest() == row['sha256']
for row in json.loads((C/'inputs.json').read_text()):
    assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest() == row['sha256']
for name in ('duplex.c','duplex.h'):
    (R/'app/k7sound'/name).write_bytes((C/'candidate'/name).read_bytes())
p = R/'app/k7sound/k7sound_main.c'
s = p.read_text()
old = '  bool loopback = !strcmp(argv[1], "loopback");'
assert old in s
s = s.replace(old, '  bool route_all = !strcmp(argv[1], "loopback-rxall");\n  bool loopback = route_all || !strcmp(argv[1], "loopback");')
old = 'rc = dl_run(&dl, platform.ready, 1, 4096000, loop_capture, 512,\n                  128, &loop_result);'
assert old in s
s = s.replace(old, 'rc = dl_run_route(&dl, platform.ready, 1, 4096000, loop_capture, 512,\n                  128, route_all ? DL_ROUTE_RX_ALL_SDI0 : DL_ROUTE_DEFAULT, &loop_result);')
p.write_text(s, newline='\n')
p = R/'tools/sync_sdk.py'
s = p.read_text()
assert "'audio-filter-20260910')" in s
s = s.replace("'audio-filter-20260910')", "'audio-filter-20260910', 'audio-loopback-20260910')")
p.write_text(s,newline='\n')
p = R/'tools/observe_audio_io.py'
s = p.read_text().replace("'audio-loopback-20260910'],", "'audio-loopback-20260910','audio-route-20260910'],")
s = s.replace("'k7sound loopback'],", "'k7sound loopback','k7sound loopback-rxall'],")
s = s.replace("'audio-loopback-20260910':'verify_audio_loopback_image'}", "'audio-loopback-20260910':'verify_audio_loopback_image','audio-route-20260910':'verify_audio_route_image'}")
p.write_text(s,newline='\n')
E = R/'evidence/audio-route-20260910'
E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256='c861e97a8436e954ba57c70ba0766c244be7d6e74185e7610627eb682f0eae8d',frames=128,changed_register_field='PATH RX route bits 15:8 only',default_loopback_preserved=True,amp_enable=False,hardware_tested=False),indent=2))
print('Explicit RX route candidate integrated; build and RAM validation pending')
