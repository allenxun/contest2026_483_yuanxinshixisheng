"""Add a numbered source to silent loopback; no route or clock change."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
C = R/'work-in-progress/parallel-neon-probe-medium/audio-marker-v1'
want='4442f2544ed7587cbd0eede0ac7260dbfc3e1d3ae9da3f20bda1bc4bfe6f2b9b'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()==want
for row in json.loads((C/'outputs.json').read_text()):
    assert hashlib.sha256((C/row['path']).read_bytes()).hexdigest()==row['sha256']
for row in json.loads((C/'inputs.json').read_text()):
    assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256']
for name in ('duplex.c','duplex.h'):
    (R/'app/k7sound'/name).write_bytes((C/'candidate'/name).read_bytes())
p=R/'app/k7sound/k7sound_main.c'; s=p.read_text()
old='  bool route_all = !strcmp(argv[1], "loopback-rxall");'
assert old in s
s=s.replace(old,'  bool numbered = !strcmp(argv[1], "loopback-numbered");\n'+old)
s=s.replace('bool loopback = route_all ||', 'bool loopback = numbered || route_all ||')
old='      rc = dl_run_route(&dl, platform.ready, 1, 4096000, loop_capture, 512,\n                  128, route_all ? DL_ROUTE_RX_ALL_SDI0 : DL_ROUTE_DEFAULT, &loop_result);'
assert old in s
s=s.replace(old,'      if (numbered)\n        rc = dl_run_numbered(&dl, platform.ready, 1, 4096000, loop_capture, 512, &loop_result);\n      else\n        '+old.strip())
p.write_text(s,newline='\n')
p=R/'tools/sync_sdk.py'; s=p.read_text()
assert "'audio-loopback-20260910')" in s
s=s.replace("'audio-loopback-20260910')","'audio-loopback-20260910', 'audio-route-20260910')")
p.write_text(s,newline='\n')
p=R/'tools/observe_audio_io.py'; s=p.read_text()
s=s.replace("'audio-route-20260910'],","'audio-route-20260910','audio-marker-20260910'],")
s=s.replace("'k7sound loopback-rxall'],","'k7sound loopback-rxall','k7sound loopback-numbered'],")
s=s.replace("'audio-route-20260910':'verify_audio_route_image'}","'audio-route-20260910':'verify_audio_route_image','audio-marker-20260910':'verify_audio_marker_image'}")
p.write_text(s,newline='\n')
E=R/'evidence/audio-marker-20260910'; E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256=want,frames=128,
    change='Numbered marker source only; default RX route required',amp_enable=False,hardware_tested=False),indent=2))
print('Numbered silent loopback integrated; build gates pending')
