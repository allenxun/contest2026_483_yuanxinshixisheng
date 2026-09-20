"""One explicitly requested live ASR then echo TTS; requires --echo-test bridge."""
import time
from cloud_radio_stage_audit import remote, ROOT

code = r'''
import serial,time,json
with serial.Serial('/dev/ttyUSB0',1500000,timeout=.02,write_timeout=2) as s:
 s.dtr=False;s.rts=False
 origin=time.monotonic()
 for command, marker in [('k7sound tone-max',b'SOUND result=0'),('k7cloud asr-live 10.3.1.125',b'frames_sent=150 completed=1'),('k7cloud tts-test 10.3.1.125',b'K7CLOUD tts result=0')]:
  start=time.monotonic()
  for c in command.encode()+b'\r':s.write(bytes([c]));s.flush();time.sleep(.004)
  out=bytearray();end=time.monotonic()+65
  while time.monotonic()<end:
   out.extend(s.read(8192))
   if b'nsh>' in out:break
  print(out.decode(errors='replace'),flush=True)
  print('ECHO_TIMING '+json.dumps({'command':command.split()[1],'command_ms':round((time.monotonic()-start)*1000),'elapsed_ms':round((time.monotonic()-origin)*1000),'passed':marker in out}),flush=True)
  if marker not in out:break
  if command=='k7sound tone-max':origin=time.monotonic()
'''
result=remote(code)
directory=ROOT/'evidence/cloud-echo-20260915';directory.mkdir(parents=True,exist_ok=True)
(directory/(time.strftime('%H%M%S')+'.log')).write_bytes(result)
for line in result.decode(errors='replace').splitlines():
 if 'K7CLOUD' in line or 'ECHO_TIMING' in line:print(line)
