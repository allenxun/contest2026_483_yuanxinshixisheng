"""Use existing Windows ASR on raw/filtered PGA24 recording; no board claims."""
import hashlib
import json
import struct
import subprocess
import time
import wave
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R/'evidence/audio-filter-20260910/pga24-host-asr'
O.mkdir(exist_ok=False)
baseline = json.loads((R/'evidence/audio-gain-20260910/voice-max-first/host-asr-unmodified-left/result.json').read_text())
inputs = [R/'evidence/audio-input-20260910/voice-pga24-first/capture-raw32.wav',
          R/'evidence/audio-filter-20260910/pga24-host-comparison/ma4.wav',
          R/'evidence/audio-filter-20260910/pga24-host-comparison/ma4-hp80.wav']
rows = []
for i, source in enumerate(inputs):
    original = source.read_bytes()
    with wave.open(str(source), 'rb') as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate()) == (2,4,16000)
        n = w.getnframes()
        words = struct.unpack('<'+'i'*(2*n), w.readframes(n))
    mono = struct.pack('<'+'h'*n, *(words[2*j] >> 16 for j in range(n)))
    target = O/('input-%d-left.wav' % i)
    with wave.open(str(target), 'wb') as w:
        w.setparams((1,2,16000,n,'NONE','not compressed'))
        w.writeframes(mono)
    cmd = baseline['command'][:-1] + [str(target)]
    start = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, timeout=60)
    (O/('output-%d.raw' % i)).write_bytes(p.stdout)
    (O/('error-%d.raw' % i)).write_bytes(p.stderr)
    assert source.read_bytes() == original
    rows.append(dict(source=str(source),sha256=hashlib.sha256(original).hexdigest(),
                     transform='left channel and arithmetic upper16 only; all frames retained',
                     command=cmd,exit_code=p.returncode,elapsed=time.monotonic()-start))
    print(i, p.returncode, p.stdout.decode(errors='replace')[-1200:], flush=True)
(O/'result.json').write_text(json.dumps(dict(host_only=True, real_board_recording=True,
    board_asr_deployed=False, audio_quality_accepted=False, nominal_rate_not_validated=True,
    cases=rows),indent=2))
