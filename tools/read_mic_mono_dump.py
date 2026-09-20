"""Read retained PCM without live SSH forwarding to reduce serial backpressure."""
from cloud_radio_stage_audit import remote,ROOT
code=r'''
import serial,time,base64,json,subprocess
if subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True).stdout.strip():raise RuntimeError('Serial owned')
s=serial.Serial(port=None,baudrate=1500000,timeout=.01,exclusive=True)
s.rts=False;s.dtr=False;s.port='/dev/ttyUSB0';s.open()
try:
 s.reset_input_buffer();s.write(b'k7sound dump\n');s.flush()
 data=bytearray();end=time.monotonic()+40
 while time.monotonic()<end:
  data.extend(s.read(s.in_waiting or 1))
  if b'SOUND_PCM_END' in data[-256:]:break
 print(base64.b64encode(data).decode())
finally:s.close()
'''
import base64,re,json,struct,wave
folder=ROOT/'evidence/stage-watch-20260916'
words={}
def absorb(data):
 for pos,values in re.findall(rb'^PCM ([0-9a-f]{6})((?: [0-9a-f]{8}){8})\r?\r?$',data,re.M):
  at=int(pos,16)
  for i,v in enumerate(values.split()):
   value=int(v,16)
   if at+i in words and words[at+i]!=value:raise RuntimeError('Retained PCM changed or dump corrupted')
   words[at+i]=value
for name in ['mic-replay-mono.log']:
 absorb((folder/name).read_bytes())
for attempt in range(8):
 if len(words)==96000:break
 data=base64.b64decode(remote(code))
 (folder/('mic-mono-extra-%d.log'%attempt)).write_bytes(data)
 absorb(data);print('attempt',attempt,'valid_words',len(words),flush=True)
(folder/'mic-mono-coverage.json').write_text(json.dumps({'words':len(words),'expected':96000,'complete':len(words)==96000}))
if len(words)!=96000:raise RuntimeError('Incomplete recording; no WAV emitted')
for ch in [0,1]:
 with wave.open(str(folder/('mic-mono-channel-%d.wav'%ch)),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
  w.writeframes(b''.join(struct.pack('<H',words[i]>>16) for i in range(ch,96000,2)))
print('Complete retained recording reconstructed without conflicting samples')
