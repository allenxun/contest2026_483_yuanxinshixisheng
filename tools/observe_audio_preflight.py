"""One bounded read-only CRU/IOC observation after verified RAM boot."""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/audio-preflight-20260910'
sys.path.insert(0, str(ROOT.parent / '无线适配_2026-09-08/tools/pydeps'))
import serial
from verify_audio_preflight_image import verify


def main():
    image = verify(ROOT / 'artifacts/audio-preflight-20260910')
    assert 'PASS: REAL K7 NSH' in (OUT / 'ramload-progress.txt').read_text(encoding='utf-8-sig')
    assert json.loads((OUT / 'affinity-boot.json').read_text())['passed']
    raw = bytearray()
    prompt = False
    port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
    port.dtr = False
    port.rts = False
    port.port = 'COM8'
    with (OUT / 'preflight.bin').open('xb') as evidence:
        with port:
            port.write(b'k7audio preflight\r')
            port.flush()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                data = port.read(8192)
                evidence.write(data)
                raw.extend(data)
                if re.search(rb'nsh>\s*(?:\x1b\[K)?$', raw):
                    prompt = True
                    break
    expected = [0x27200300, 0x27200304, 0x272003dc, 0x272003e4,
                0x27200800, 0x2720082c, 0x27200830, 0x2604408c]
    rows = re.findall(rb'AUDIO_PREFLIGHT snapshot=([01]) address=([0-9a-f]{8}) value=([0-9a-f]{8})', raw)
    snapshots = [[(int(a, 16), int(v, 16)) for p, a, v in rows if int(p) == n] for n in (0, 1)]
    complete = prompt and len(rows) == 16 and all([a for a, _ in s] == expected for s in snapshots)
    marker = b'AUDIO_PREFLIGHT result=0 writes=0 i2c_transactions=0 actual_rate_known=0 audio_ready=0'
    complete = complete and raw.count(marker) == 1
    report = dict(passed=complete, image=image,
                  raw_sha256=hashlib.sha256(raw).hexdigest(),
                  snapshots=[{hex(a): hex(v) for a, v in s} for s in snapshots],
                  snapshots_identical=complete and snapshots[0] == snapshots[1],
                  scope='Read-only clock/mux snapshot; no actual rate or codec availability proof',
                  i2c_transactions=0, audio_ready=False, emmc_written=False)
    with (OUT / 'preflight.json').open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
    print(json.dumps(report))
    if not complete:
        raise SystemExit('Incomplete observation; target left untouched')


if __name__ == '__main__':
    main()
