"""Single cued recording, quiet replay and diagnostic PCM dump; no motion."""
import subprocess
from pathlib import Path
from cloud_radio_stage_audit import SSH
code=r'''
import serial,time,subprocess
if subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True).stdout.strip():raise RuntimeError('Serial owned')
s=serial.Serial(port=None,baudrate=1500000,timeout=.2,exclusive=True)
s.rts=False;s.dtr=False;s.port='/dev/ttyUSB0';s.open()
def command(cmd,marker,timeout):
 s.write((cmd+'\n').encode());s.flush();data='';end=time.monotonic()+timeout
 while time.monotonic()<end:
  x=s.read(8192).decode(errors='replace');data+=x;print(x,end='',flush=True)
  if marker in data:return data
 raise RuntimeError('Missing completion for '+cmd)
try:
 result=command('k7sound capture-cued 48000','SOUND result=',12)
 if 'SOUND result=0' not in result:raise RuntimeError('Capture failed')
 time.sleep(.5)
 command('k7sound replay 6','SOUND result=',10)
 command('k7sound dump','SOUND_PCM_END',35)
finally:s.close()
'''
out=Path(__file__).resolve().parents[1]/'evidence/stage-watch-20260916/mic-replay-diagnostic.log'
with out.open('w',encoding='utf-8') as f:
 p=subprocess.Popen(SSH+['python3 -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 p.stdin.write(code.encode());p.stdin.close()
 for raw in iter(p.stdout.readline,b''):
  line=raw.decode(errors='replace');f.write(line);f.flush()
  if any(k in line for k in ['SOUND cue','SOUND pcm','SOUND result','SOUND_PCM','Error']):print(line,end='',flush=True)
 raise SystemExit(p.wait())
