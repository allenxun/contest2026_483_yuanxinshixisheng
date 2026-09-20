"""Compile the integrated C source; compare captured PGA24 WAV without I/O."""
import ctypes
import hashlib
import json
import subprocess
import wave
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R/'evidence/audio-filter-20260910/pga24-host-comparison'
O.mkdir(parents=True, exist_ok=False)
source = R/'evidence/audio-input-20260910/voice-pga24-first/capture-raw32.wav'
before = source.read_bytes()
assert hashlib.sha256(before).hexdigest() == '0f176ee9294277215820006b2a0f164947747929bc2cd74bdadd6f4f33b6b993'
c = R/'app/k7sound/playback_filter.c'
h = R/'app/k7sound/playback_filter.h'
cmd = ['D:/software/mingw64/mingw64/bin/gcc.exe', '-std=c11', '-O2',
       '-Wall', '-Wextra', '-Wconversion', '-Werror', '-shared', str(c),
       '-o', str(O/'filter.dll')]
p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
assert p.returncode == 0, p.stderr
lib = ctypes.CDLL(str(O/'filter.dll'))
fn = lib.af_filter
ptr = ctypes.POINTER(ctypes.c_uint32)
fn.argtypes = [ptr, ctypes.c_size_t, ptr, ctypes.c_size_t,
               ctypes.c_uint, ctypes.c_int, ptr]
fn.restype = ctypes.c_int
with wave.open(str(source), 'rb') as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 4, 16000)
    n = w.getnframes()
    raw = w.readframes(n)
buf = (ctypes.c_uint32*(2*n)).from_buffer_copy(raw)
rows = []
for mode in (1, 2):
    dest = (ctypes.c_uint32*(2*n))()
    sat = ctypes.c_uint32(99)
    rc = fn(buf, 2*n, dest, 2*n, n, mode, ctypes.byref(sat))
    assert rc == 0 and bytes(buf) == raw
    path = O/('ma4.wav' if mode == 1 else 'ma4-hp80.wav')
    with wave.open(str(path), 'wb') as w:
        w.setparams((2, 4, 16000, n, 'NONE', 'not compressed'))
        w.writeframes(bytes(dest))
    rows.append(dict(mode=mode, frames=n, saturations=sat.value,
                     file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert source.read_bytes() == before
report = dict(command=cmd, stdout=p.stdout, stderr=p.stderr,
              source=str(source), source_sha256=hashlib.sha256(before).hexdigest(),
              code={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (c,h)},
              results=rows, host_only=True, raw_preserved=True,
              nominal_rate_not_validated=True, audio_quality_accepted=False)
(O/'result.json').write_text(json.dumps(report, indent=2))
print(json.dumps(rows))
