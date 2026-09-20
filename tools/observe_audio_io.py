"""Bounded audio console command with raw, version-scoped evidence."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import time

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial

p = argparse.ArgumentParser()
p.add_argument('--revision', choices=['audio-io-b-20260910','audio-sound-20260910','audio-fifo-20260910','audio-normal-20260910','audio-mic-20260910','audio-rxtrace-20260910','audio-reset-20260910','audio-gain-20260910','audio-input-20260910','audio-filter-20260910','audio-loopback-20260910','audio-route-20260910','audio-marker-20260910','audio-rx2-20260910','audio-guard-20260910'], required=True)
p.add_argument('--command', choices=['k7audiohw codec-probe','k7sound probe','k7sound tone','k7sound capture','k7sound capture 48000','k7sound capture-common 48000','k7sound capture-vmid 48000','k7sound dump','k7sound replay','k7sound capture-reset','k7sound capture-reset 48000','k7sound tone-reset','k7sound capture-clear','k7sound capture-clear 48000','k7sound tone-clear','k7sound capture-clockwait','k7sound capture-clockwait 48000','k7sound tone-clockwait','k7sound replay 6','k7sound replay 12','k7sound replay 18','k7sound replay 24','k7sound tone 6','k7sound tone 12','k7sound tone 18','k7sound tone 24','k7sound replay-max','k7sound tone-max','k7sound capture-pga24','k7sound capture-pga24 48000','k7sound replay-ma4-max','k7sound replay-hp-max','k7sound loopback','k7sound loopback-rxall','k7sound loopback-numbered','k7sound loopback-rx2','k7sound loopback-guard'], required=True)
a = p.parse_args()
module = {'audio-io-b-20260910':'verify_audio_io_b_image', 'audio-sound-20260910':'verify_audio_sound_image', 'audio-fifo-20260910':'verify_audio_fifo_image', 'audio-normal-20260910':'verify_audio_normal_image', 'audio-mic-20260910':'verify_audio_mic_image', 'audio-rxtrace-20260910':'verify_audio_rxtrace_image', 'audio-reset-20260910':'verify_audio_reset_image', 'audio-gain-20260910':'verify_audio_gain_image', 'audio-input-20260910':'verify_audio_input_image','audio-filter-20260910':'verify_audio_filter_image','audio-loopback-20260910':'verify_audio_loopback_image','audio-route-20260910':'verify_audio_route_image','audio-marker-20260910':'verify_audio_marker_image','audio-rx2-20260910':'verify_audio_rx2_image','audio-guard-20260910':'verify_audio_guard_image'}[a.revision]
image = importlib.import_module(module).verify(R/'artifacts'/a.revision)
out = R/'evidence'/a.revision
assert 'PASS: REAL K7 NSH' in (out/'ramload-progress.txt').read_text(encoding='utf-8-sig')
stamp = time.strftime('%Y%m%d-%H%M%S')
stem = a.command.replace(' ', '-')+'-'+stamp
s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
s.dtr = False
s.rts = False
s.port = 'COM8'
raw = bytearray()
seen = False
started = time.monotonic()
with (out/(stem+'.bin')).open('xb') as log:
    with s:
        s.write(a.command.encode('ascii')+b'\r')
        s.flush()
        while time.monotonic()-started < 30:
            data = s.read(8192)
            raw.extend(data)
            log.write(data)
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
                seen = True
                break
report = dict(image=image, command=a.command, prompt=seen,
              elapsed_seconds=time.monotonic()-started,
              raw_sha256=hashlib.sha256(raw).hexdigest(), raw=stem+'.bin')
with (out/(stem+'.json')).open('x') as f:
    json.dump(report, f, indent=2)
print(raw.decode(errors='replace')[-9000:] if 'dump' not in a.command else 'PCM raw data saved: '+str(out/(stem+'.bin')))
print(json.dumps(report))
if not seen: raise SystemExit('Audio command observation timed out; inspect saved raw output')
