"""Initialize UVC and negotiate its mode, without streaming or motion."""
import argparse
import subprocess
from datetime import datetime, timezone
from cloud_radio_stage_audit import ROOT, remote

p=argparse.ArgumentParser()
p.add_argument('--start',action='store_true')
p.add_argument('--probe',action='store_true')
args=p.parse_args()
commands=[]
if args.start:commands.append(('k7host start','K7 host start result=0'))
commands.append(('k7host camera','camera connected=1'))
if args.probe:commands.append(('k7host probe','committed=1'))
code=r'''
import serial,time
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for command,marker in COMMANDS:
  pending=s.read(8192)
  if pending:print(pending.decode(errors='replace'),flush=True)
  for c in command.encode()+bytes([13]):s.write(bytes([c]));s.flush();time.sleep(.004)
  raw=bytearray();end=time.monotonic()+15
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if marker.encode() in raw and b'nsh>' in raw:break
  print(raw.decode(errors='replace'),flush=True)
  if marker.encode() not in raw:raise RuntimeError('Not ready: '+command)
  time.sleep(3 if command=='k7host start' else .5)
'''.replace('COMMANDS',repr(commands))
ok=True
try:raw=remote(code)
except subprocess.CalledProcessError as exc:raw=exc.output or b'';ok=False
out=ROOT/'evidence/vision-ble-coexist-20260915'
name='camera-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log'
(out/name).write_bytes(raw)
for line in raw.decode(errors='replace').splitlines():
 if any(word in line for word in ('camera connected','K7 CAMERA','K7 host','K7 HUB','probe result','committed','error','failed')):
  print(line)
print('evidence',name,'passed',ok)
if not ok:raise SystemExit(1)
