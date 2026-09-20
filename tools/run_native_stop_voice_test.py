"""User-prepared human stop-command test. No camera-start command is issued."""
from datetime import datetime,timezone
import subprocess
from cloud_radio_stage_audit import remote,ROOT
code=r'''
import serial,time
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 for command,marker in [('k7sound tone-max',b'SOUND result=0'),
                        ('k7cloud device-once 10.3.1.125',b'K7CLOUD device result=0')]:
  for c in command.encode()+b'\r':s.write(bytes([c]));s.flush();time.sleep(.004)
  raw=bytearray();end=time.monotonic()+45
  while time.monotonic()<end:
   raw.extend(s.read(8192))
   if marker in raw:break
  print(raw.decode(errors='replace'),flush=True)
  if marker not in raw:raise RuntimeError('native stop test command failed')
  if 'device-once' in command and b'K7CLOUD device intent=3' not in raw:
   raise RuntimeError('stop intent not recognized; no acceptance')
'''
failure=None
try:raw=remote(code)
except subprocess.CalledProcessError as exc:raw=exc.output or b'';failure=exc
path=ROOT/'evidence/device-intent-20260915'/('native-stop-'+datetime.now(timezone.utc).strftime('%H%M%S')+'.log')
path.write_bytes(raw)
print('\n'.join(line for line in raw.decode(errors='replace').splitlines()
                if 'K7CLOUD' in line or 'SOUND result=' in line))
if failure:raise SystemExit(1)

