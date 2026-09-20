"""One harmless NSH background echo to inspect prompt ordering, no radio change."""
import sys, time, json
from pathlib import Path
from smp_console_config import console_baud
R=Path(__file__).resolve().parents[1];E=R/'evidence/smp-load-20260910'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=console_baud(R,E.name),timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';raw=bytearray()
assert not (E/'background-echo.bin').exists()
with s:
    s.write(b'echo VV_BG_CHECK &\r');s.flush();end=time.monotonic()+2
    while time.monotonic()<end:raw.extend(s.read(8192))
(E/'background-echo.bin').write_bytes(raw)
print(json.dumps(dict(console=raw.decode('ascii',errors='replace'))))
