"""Query the running board and exercise only its three-second PCM diagnostic."""
from cloud_radio_stage_audit import remote, ROOT
import subprocess,time
CODE=r'''
import serial,time
with serial.Serial('/dev/ttyUSB0',1500000,timeout=.03,write_timeout=2) as s:
 s.dtr=False;s.rts=False
 for cmd in ['', 'k7radio provision-status','k7cloud capture-stream-check','k7radio host-status','k7radio provision-status']:
  for c in cmd.encode()+b'\r':
   s.write(bytes([c]));s.flush();time.sleep(.004)
  result=bytearray();deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   result.extend(s.read(8192))
   if b'nsh>' in result:break
  print(result.decode(errors='replace'),flush=True)
  if b'nsh>' not in result:raise RuntimeError('console timeout')
  time.sleep(.5)
'''
if __name__=='__main__':
 try: result=remote(CODE)
 except subprocess.CalledProcessError as e: result=e.output
 path=ROOT/'evidence/capture-stream-20260914'/('board-'+time.strftime('%H%M%S')+'.log')
 path.write_bytes(result)
 print(result.decode(errors='replace'))
