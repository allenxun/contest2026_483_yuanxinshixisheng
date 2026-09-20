"""Verify fixed speech playback on the newly booted, not-yet-networked K7."""
from cloud_radio_stage_audit import ROOT,remote
code=r'''
import serial,time,re,json
from pathlib import Path
p=Path('/home/swl/openvela/work/velavision-project/evidence/photo-retry-20260916')
s=serial.Serial(port=None,baudrate=1500000,timeout=.03,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
def command(cmd,timeout):
 for c in (cmd+'\r').encode():s.write(bytes([c]));s.flush();time.sleep(.004)
 b=bytearray();end=time.monotonic()+timeout
 while time.monotonic()<end:
  b.extend(s.read(8192))
  if b'nsh>' in b:
   with (p/'offline-prompt.log').open('ab') as log:log.write(b)
   time.sleep(.8);return bytes(b)
 with (p/'offline-prompt.log').open('ab') as log:log.write(b)
 raise RuntimeError('command timeout: '+cmd)
with s:
 radio=command('k7cloud radio-status',8)
 network=re.search(rb'wifi=([01]) ipv4_ready=([01])',radio)
 assert network,'Missing network status'
 # Deliberately unreachable service address: fixed prompt must not connect to it.
 speech=command('k7cloud tts-prompt 127.0.0.1 tracking_stopped',25)
 assert re.search(rb'local_prompt key=tracking_stopped bytes=\d+ result=0',speech),speech
 print(json.dumps({'wifi':int(network[1]),'ipv4_ready':int(network[2]),'local_prompt':'tracking_stopped','playback_result':0,'cloud_address':'127.0.0.1','human_hearing_confirmed':False}))
'''
result=remote(code)
(ROOT/'evidence/photo-retry-20260916/offline-prompt.json').write_bytes(result)
print(result.decode())
