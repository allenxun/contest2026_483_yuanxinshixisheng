from cloud_radio_stage_audit import remote,ROOT
code='''import serial,time
s=serial.Serial('/dev/ttyUSB0',1500000,timeout=.05,write_timeout=2)
s.dtr=False;s.rts=False
with s:
 for cmd in ['', 'k7radio wifi-service-start','k7radio host-status','k7radio provision-status']:
  for c in cmd.encode()+b'\\r':s.write(bytes([c]));s.flush();time.sleep(.004)
  end=time.monotonic()+8;b=bytearray()
  while time.monotonic()<end:
   b.extend(s.read(8192))
   if b'nsh>' in b:break
  print(bytes(b).decode(errors='replace'),flush=True)
  if b'nsh>' not in b:raise RuntimeError('console timeout')
  time.sleep(.5)
'''
if __name__=='__main__':
 import subprocess
 try: result=remote(code)
 except subprocess.CalledProcessError as e: result=e.output
 (ROOT/'evidence/ble-cloud-start-20260914/console-probe.log').write_bytes(result)
 print(result.decode())
