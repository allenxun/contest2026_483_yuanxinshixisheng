"""Start only after the user is ready. Board owns all conversation rounds."""
import argparse,subprocess,json
from datetime import datetime,timezone
from cloud_radio_stage_audit import ROOT,SSH
p=argparse.ArgumentParser();p.add_argument('--start',action='store_true');p.add_argument('--rounds',type=int,default=3);a=p.parse_args()
assert 1<=a.rounds<=3
if not a.start:print('Ready; --start records real microphone audio.');raise SystemExit(0)
code=r"""
import serial,time
s=serial.Serial(port=None,baudrate=1500000,timeout=.05,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s:
 def readfor(t):
  b=bytearray();end=time.monotonic()+t
  while time.monotonic()<end:b.extend(s.read(8192))
  return b
 readfor(.5);s.write(bytes([13]));s.flush();readfor(.3)
 s.write(b'k7cloud chat-loop 10.3.1.125 ROUNDS &'+bytes([13]));s.flush()
 b=bytearray();end=time.monotonic()+340
 while time.monotonic()<end:
  chunk=s.read(8192)
  if chunk:
   b.extend(chunk);print(chunk.decode(errors='replace'),end='',flush=True)
  if b'K7CLOUD chat loop_done=' in b:
   print(readfor(1).decode(errors='replace'),flush=True);break
 else:raise RuntimeError('Observation timeout; check board before restarting any capture')
""".replace('ROUNDS',str(a.rounds))
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'evidence/native-chat-cue-20260915'/('human-'+stamp+'.log')
with out.open('wb') as log:
 child=subprocess.Popen(SSH[:-1]+['-o','ConnectTimeout=8',SSH[-1],'python3 -u -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 child.stdin.write(code.encode());child.stdin.close()
 while True:
  line=child.stdout.readline()
  if not line:break
  log.write(line);log.flush()
  text=line.decode(errors='replace')
  if any(key in text for key in ['K7CLOUD','SOUND cue','SOUND result=','Traceback','Error']):print(text,end='',flush=True)
 result=child.wait()
print('EVIDENCE',out,'exit',result,flush=True)
raise SystemExit(result)
