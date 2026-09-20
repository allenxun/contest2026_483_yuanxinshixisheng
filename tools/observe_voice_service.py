"""Read-only native service task/status snapshot; never starts RF work."""
import sys,time,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
E=R/'evidence/voice-cold-20260910'/('service-status-'+time.strftime('%Y%m%d-%H%M%S'))
E.mkdir()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
with s:
    for name,cmd in [('tasks','ps'),('host','k7radio host-status'),('wifi','k7radio wifi-status')]:
        s.write(cmd.encode()+b'\r');s.flush();data=bytearray();end=time.monotonic()+5
        while time.monotonic()<end:
            data.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',data):break
        (E/(name+'.bin')).write_bytes(data)
        print(data.decode(errors='replace'),flush=True)
