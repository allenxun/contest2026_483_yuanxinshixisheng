"""Run the bounded pause capture diagnostic; result is not usable audio."""
import re,time
from pathlib import Path
import serial
r=Path(__file__).resolve().parent
with (r/('reject-'+time.strftime('%Y%m%d-%H%M%S')+'.log')).open('xb') as log:
    s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
    s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
    def read(seconds):
        data=bytearray();end=time.monotonic()+seconds
        while time.monotonic()<end:
            data.extend(s.read(4096))
            if re.search(rb'nsh> ',data):break
        log.write(data);log.flush();print(data.decode(errors='replace'),flush=True)
        return data
    try:
        s.write(b'\r');assert b'nsh>' in read(2)
        s.write(b'k7voice asr-mic\r')
        data=read(10)
        assert b'nsh>' in data,'Command did not return'
    finally:s.close()


