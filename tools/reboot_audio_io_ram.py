"""Stop owned native Wi-Fi, reboot once and interrupt at U-Boot. No flash."""
import sys,time,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
from verify_audio_io_image import verify
verify(R/'artifacts/audio-io-20260910')
out=R/'evidence/audio-io-20260910';out.mkdir(exist_ok=True)
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
with s:
 s.write(b'k7radio wifi-disconnect\r');s.flush()
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:s.read(8192)
 s.write(b'k7radio wifi-status\r');s.flush();buf=bytearray();deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  buf.extend(s.read(8192))
  if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):break
 assert b'WIFI status active=0' in buf,'Network cleanup incomplete; reboot prevented'
 s.write(b'reboot\r');s.flush();buf=bytearray();deadline=time.monotonic()+25
 while time.monotonic()<deadline:
  buf.extend(s.read(8192));s.write(b'\x03');s.flush()
  if re.search(rb'(?:\r?\n)=>\s*$',buf):break
 else:raise RuntimeError('U-Boot prompt not observed')
 
 with (out/'reboot.bin').open('xb') as log:log.write(buf)
 print('PASS: U-Boot prompt; flash untouched')
