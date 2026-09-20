"""Verify persistent native service across independent scan commands."""
import json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/voice-owner-20260910'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
from verify_voice_owner_image import verify
verify(R/'artifacts/voice-owner-20260910')
O=E/('lifetime-'+time.strftime('%Y%m%d-%H%M%S'));O.mkdir()
results=[]
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
with s:
 for name,cmd in [('before','ps'),('scan2','k7voice scan'),('scan3','k7voice scan'),('after','ps'),('host','k7radio host-status'),('wifi','k7radio wifi-status')]:
  start=time.monotonic();deadline=start+(40 if name.startswith('scan') else 5)
  s.write(cmd.encode()+b'\r');s.flush();raw=bytearray();prompt=False
  while time.monotonic()<deadline:
   raw.extend(s.read(8192))
   if re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
  (O/(name+'.bin')).write_bytes(raw)
  passed=prompt
  result=dict(stage=name,seconds=time.monotonic()-start,prompt=prompt)
  if name.startswith('scan'):
   match=re.search(rb'VOICE scan_done id=(\d+) count=(\d+)',raw)
   passed=passed and bool(match) and int(match[2])>0
   if match:result.update(id=int(match[1]),count=int(match[2]))
   result['lansee_seen']=b'VOICE AP ssid_hex=4c616e736565\r' in raw
  elif name in ('before','after'):
   passed=passed and b'k7_wifi_svc' in raw
   result['service_task_present']=b'k7_wifi_svc' in raw
  elif name=='host':passed=passed and b'host_mode=1 fault=0' in raw
  elif name=='wifi':result['online']=b'WIFI status active=1' in raw
  result['passed']=passed;results.append(result)
  (O/'result.json').write_text(json.dumps(dict(results=results,speech_tested=False),indent=2))
  print(json.dumps(result),flush=True)
  if not passed:raise RuntimeError('Gate failed: '+name)
