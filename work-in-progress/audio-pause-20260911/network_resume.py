"""Bounded wireless service and real scan check; no credentials or join."""
import json,re,time
from pathlib import Path
import serial
r=Path(__file__).resolve().parent/('network-resume-'+time.strftime('%Y%m%d-%H%M%S'));r.mkdir()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
rows=[]
try:
    for name,cmd,limit,marker in [('host','k7radio host-status',5,b'host_mode=1 fault=0'),('service','k7radio wifi-service-start',15,b'WIFI shared start ret=0'),('scan','k7voice scan',40,b'VOICE scan_done')]:
        s.write((cmd+'\r').encode());data=bytearray();end=time.monotonic()+limit
        while time.monotonic()<end:
            data.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',data):break
        (r/(name+'.log')).write_bytes(data)
        passed=marker in data and b'nsh>' in data
        rows.append(dict(stage=name,passed=passed));print(data.decode(errors='replace'),flush=True)
        (r/'result.json').write_text(json.dumps(dict(stages=rows,wifi_connected=False,phone_gatt_verified=False),indent=2))
        if not passed:raise RuntimeError('Failed stage '+name)
finally:s.close()

