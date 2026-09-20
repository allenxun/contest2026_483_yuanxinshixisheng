"""Verify new stage TTS on an already provisioned board; never moves gimbal."""
from datetime import datetime,timezone
import subprocess
from cloud_radio_stage_audit import remote,ROOT
code=r'''
import serial,time,json
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for command,marker in [('k7cloud radio-status',b'wifi=1 ipv4_ready=1'),
                        ('k7cloud tts-prompt 10.3.1.125 tracking_stopped',b'K7CLOUD prompt_done result=0')]:
  for c in command.encode()+b'\r':s.write(bytes([c]));s.flush();time.sleep(.004)
  raw=bytearray();end=time.monotonic()+(8 if 'radio-status' in command else 45)
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if b'nsh>' in raw:break
  print(raw.decode(errors='replace'))
  if marker not in raw:raise RuntimeError('board stage verification failed')
'''
failure=None
try:
 raw=remote(code)
except subprocess.CalledProcessError as exc:
 raw=exc.output or b'';failure=exc
out=ROOT/'evidence/device-intent-20260915'
(out/('stage-prompt-'+datetime.now(timezone.utc).strftime('%H%M%S')+'.log')).write_bytes(raw)
print(raw.decode(errors='replace'))
if failure:raise SystemExit(1)

