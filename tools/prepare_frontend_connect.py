"""Leave tested radio service ready for frontend scan -> connect validation.
Explicitly stops Wi-Fi because this firmware cannot scan while online.
"""
import json,re,sys,time
from datetime import datetime,timezone
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/ble-connect-20260909'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
rows=[json.loads(x) for x in (E/'ble-connect-01.jsonl').read_text().splitlines()]
assert any(x['event']=='PASS' for x in rows)
s=serial.Serial(port=None,baudrate=1500000,timeout=.03,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';records=[]
safe=re.compile(r'^(WIFI (status|netdev|AMSDU|link cleanup|IP worker stopped)|RADIO BLE (name=|history)|PROV registered=)')
with s:
 for cmd in ['k7radio wifi-disconnect','k7radio wifi-status','k7radio ble-status','k7radio provision-status']:
  s.write(cmd.encode()+b'\r');s.flush();buf=bytearray();end=time.monotonic()+(5 if cmd.endswith('wifi-disconnect') else 2)
  while time.monotonic()<end:buf.extend(s.read(8192))
  lines=[line.strip() for line in buf.decode('ascii',errors='replace').splitlines() if safe.match(line.strip())]
  records.append(dict(time=datetime.now(timezone.utc).isoformat(),command=cmd,lines=lines))
assert any('WIFI status active=0 wifi_connected=0' in line for row in records for line in row['lines'])
with (E/'frontend-ready.json').open('x',encoding='utf-8') as f:json.dump(dict(wifi_intentionally_stopped_for_scan=True,records=records),f,indent=2)
print('PASS: native Wi-Fi stopped for frontend scan; BLE service retained')
