"""Read-only MMU command bound to verified current ELF; exclusive COM8 use."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from verify_audio_mmu_image import verify

R = Path(__file__).resolve().parents[1]
REV = 'audio-mmu-20260910'
image = verify(R/'artifacts'/REV)
out = R/'evidence'/REV
progress = (out/'ramload-progress.txt').read_text(encoding='utf-8-sig')
assert 'PASS: REAL K7 NSH' in progress and image['sha256'] in progress
binder = R/'work-in-progress/parallel-neon-probe-medium/audio-mmu-integration-v1/bind_elf.py'
assert hashlib.sha256(binder.read_bytes()).hexdigest() == '0eca3b6b8b184292cb4afdd6344379f066940201b1a331885a05d040f123aa36'
spec = importlib.util.spec_from_file_location('mmu_binding', binder)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
binding = module.bind(R/'artifacts'/REV/'nuttx', R/'evidence/build'/REV/'verification.json', R/'evidence/audio-mmu-input-20260911')
sys.path.insert(0, str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
stem = 'mmu-'+time.strftime('%Y%m%d-%H%M%S')
s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
s.dtr = False
s.rts = False
s.port = 'COM8'
raw = bytearray()
prompt = False
started = time.monotonic()
with (out/(stem+'.bin')).open('xb') as log, s:
    s.write(binding['command'].encode('ascii')+b'\r')
    s.flush()
    while time.monotonic()-started < 10:
        data = s.read(8192)
        raw.extend(data)
        log.write(data)
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
            prompt = True
            break
report = dict(image=image, binding=binding, prompt=prompt,
              elapsed_seconds=time.monotonic()-started,
              raw=stem+'.bin', raw_sha256=hashlib.sha256(raw).hexdigest())
with (out/(stem+'.json')).open('x') as f:
    json.dump(report, f, indent=2)
print(raw.decode(errors='replace'))
print(json.dumps(report))
if not prompt:
    raise SystemExit('MMU observation timed out; inspect raw evidence before further device operations')
