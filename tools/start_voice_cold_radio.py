"""Bounded native service startup and real scan diagnostic, not speech acceptance."""
import json
import re
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R / 'evidence/voice-cold-20260910'
sys.path.insert(0, str(R.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial
from verify_voice_cold_image import verify

verify(R / 'artifacts/voice-cold-20260910')
assert 'PASS: REAL K7 NSH' in (E / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert json.loads((E / 'affinity-boot.json').read_text())['passed']
out = E / ('native-start-' + time.strftime('%Y%m%d-%H%M%S'))
out.mkdir(exist_ok=False)
stages = [
    ('sdio', 'k7radio sdio-boot', 40, b'nsh>'),
    ('bluetooth', 'k7radio bt-host', 35, b'connect=true advertise=0'),
    ('shared', 'k7radio wifi-service-start', 15, b'WIFI shared start ret=0'),
    ('probe', 'k7voice probe', 10, b'VOICE native_network=1 asr=0 tts=0 speech_provisioning=0'),
    ('scan', 'k7voice scan', 40, b'VOICE scan_done'),
]
s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
s.dtr = False
s.rts = False
s.port = 'COM8'
results = []
with s:
    for name, command, timeout, marker in stages:
        s.write(command.encode('ascii') + b'\r')
        s.flush()
        data = bytearray()
        deadline = time.monotonic() + timeout
        prompt = False
        while time.monotonic() < deadline:
            data.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
                prompt = True
                break
        (out / (name + '.bin')).write_bytes(data)
        passed = prompt and marker in data
        results.append(dict(stage=name, prompt=prompt, expected_marker=marker.decode(), passed=passed))
        (out / 'result.json').write_text(json.dumps(dict(speech_tested=False, stages=results), indent=2))
        print(json.dumps(results[-1]), flush=True)
        if not passed:
            raise RuntimeError('Native startup gate failed: ' + name)
