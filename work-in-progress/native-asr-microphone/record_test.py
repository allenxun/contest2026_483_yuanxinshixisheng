"""Three-second microphone recording followed by real board ASR."""
import re,time
from pathlib import Path
import serial
r=Path(__file__).resolve().parent;stamp=time.strftime('%Y%m%d-%H%M%S')
log=(r/('record-asr-'+stamp+'.log')).open('xb')
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2);s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
def read(seconds,prompt=False):
 raw=bytearray();end=time.monotonic()+seconds
 while time.monotonic()<end:
  raw.extend(s.read(4096))
  if prompt and re.search(rb'nsh> ',raw):break
 log.write(raw);log.flush();print(raw.decode(errors='replace'),flush=True);return bytes(raw)
try:
 s.write(b'\r');assert b'nsh>' in read(2,True)
 # Preparation settles ADC for one second; use console timing and user readiness.
 print('Capture command starting now; speak after one second',flush=True)
 s.write(b'k7sound capture-pga24 48000\r');raw=read(10,True)
 assert b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in raw,'Audio capture/cleanup failed'
 s.write(b'k7voice asr-mic &\r');read(45)
finally:s.close();log.close()
