"""Bounded user-requested live photo test; halt on exit."""
import subprocess
from pathlib import Path
from cloud_radio_stage_audit import SSH
code=r'''
import serial,time,subprocess
if subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True).stdout.strip():
 raise RuntimeError('Serial owned')
s=serial.Serial(port=None,baudrate=1500000,timeout=.2,exclusive=True)
s.rts=False;s.dtr=False;s.port='/dev/ttyUSB0';s.open()
def send(cmd):s.write((cmd+'\n').encode());s.flush()
def read_for(seconds):
 end=time.monotonic()+seconds;data=''
 while time.monotonic()<end:
  x=s.read(8192).decode(errors='replace');data+=x;print(x,end='',flush=True)
 return data
try:
 send('k7cloud radio-status');state=read_for(3)
 if 'ipv4_ready=1' not in state:raise RuntimeError('Network not ready')
 if 'TRACK q=' not in state:raise RuntimeError('Existing camera session not confirmed; no repeat capture')
 send('k7sound speech-volume 10');ack=read_for(1)
 if 'speech_gain_db=10 cue_gain_db=24' not in ack:raise RuntimeError('Volume not confirmed')
 send('k7cloud device-loop 10.3.1.125 12 &')
 read_for(120)
finally:
 send('k7cloud device-stop');send('k7host halt');read_for(5);s.close()
'''
out=Path(__file__).resolve().parents[1]/'evidence/stage-watch-20260916/real-photo-volume10.log'
with out.open('w',encoding='utf-8') as f:
 p=subprocess.Popen(SSH+['python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 p.stdin.write(code.encode());p.stdin.close()
 for raw in iter(p.stdout.readline,b''):
  line=raw.decode(errors='replace');f.write(line);f.flush()
  if any(k in line for k in ['K7CLOUD','PHOTO','VOICE','SOUND cue','speech_gain','Error']):print(line,end='',flush=True)
 raise SystemExit(p.wait())
