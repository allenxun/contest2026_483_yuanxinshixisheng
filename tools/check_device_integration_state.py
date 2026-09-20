"""Read-only board status over existing VM serial; no reset or motion."""
from cloud_radio_stage_audit import remote
print(remote('''import serial,time,pathlib,json
print('serial_present',pathlib.Path('/dev/ttyUSB0').exists())
try:
 s=serial.Serial(port=None,baudrate=1500000,timeout=.1,write_timeout=2,exclusive=True)
 s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
 with s:
  for cmd in ['k7cloud radio-status']:
   for c in cmd.encode()+b'\\r':s.write(bytes([c]));s.flush();time.sleep(.004)
   raw=bytearray();deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    raw.extend(s.read(4096))
    if b'nsh>' in raw:break
   print(json.dumps({'command':cmd,'lines':[line for line in raw.decode(errors='replace').splitlines() if 'K7CLOUD' in line or 'nsh>' in line]}))
except Exception as exc:print(type(exc).__name__,str(exc))
''').decode())
