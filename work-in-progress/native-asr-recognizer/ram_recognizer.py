"""Audited RAM-only staged recognizer load. No persistent writes."""
import hashlib,json,re,subprocess,sys,time,zlib
from pathlib import Path
import serial
root=Path(__file__).resolve().parent
mode=sys.argv[1]
stamp=time.strftime('%Y%m%d-%H%M%S')
log=(root/(mode+'-'+stamp+'.log')).open('xb')
def port():
 s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
 s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open();return s
def read(s,seconds,prompt=None):
 data=bytearray();end=time.monotonic()+seconds
 while time.monotonic()<end:
  data.extend(s.read(4096))
  if prompt and re.search(prompt,data):break
 log.write(data);log.flush();print(data.decode(errors='replace'),flush=True);return bytes(data)
def cmd(s,b,seconds=15):
 s.write(b);s.flush();r=read(s,seconds,rb'(?:^|\n)=> $')
 assert re.search(rb'(?:^|\n)=> $',r),'Missing U-Boot prompt'
 assert b'Unknown command' not in r and b'Usage:' not in r
 return r
def check(s,addr,n,crc):
 r=cmd(s,('crc32 %x %x\r'%(addr,n)).encode(),25)
 assert re.search(rb'==>\s+'+crc.encode()+rb'\b',r),'RAM CRC mismatch'
def reset(s,command):
 s.write(command);end=time.monotonic()+18;raw=bytearray()
 while time.monotonic()<end:
  b=s.read(4096);raw.extend(b);log.write(b);log.flush()
  if b'U-Boot 2017' in raw:s.write(b'\x03');time.sleep(.05)
  if re.search(rb'(?:^|\n)=> $',raw):break
 assert re.search(rb'(?:^|\n)=> $',raw),'Autoboot not interrupted'
def copy(s,src,dst,n):
 assert src+n<=dst or dst+n<=src
 for i in range(0,n,0x400000):cmd(s,('cp.b %x %x %x\r'%(src+i,dst+i,min(0x400000,n-i))).encode())
def download(p,digest):
 assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
 subprocess.run([sys.executable,'/home/swl/openvela/work/usb-fastboot-preflight-20260911/fastboot_ram_download.py',str(p),'--sha256',digest,'--vid','0x18d1','--pid','0x4d00','--serial','f71a9d152132db55','--audited-running-buffer','0x40c00800:0x07000000','--result',str(root/(mode+'-usb-'+stamp+'.json'))],check=True,timeout=90)
if mode=='enter':
 with port() as s:
  s.write(b'\r');assert b'nsh>' in read(s,3)
  reset(s,b'reboot\r')
  check(s,0x86000000,65526320,'b5f7ae2d')
  s.write(b'fastboot usb 1\r');read(s,3)
elif mode=='reenter':
 with port() as s:
  cmd(s,b'\x03');s.write(b'fastboot usb 1\r');read(s,3)
elif mode=='decoder':
 p=Path('/home/swl/openvela/work/native-asr-model-session/decoder.ort')
 download(p,'0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14')
 with port() as s:
  cmd(s,b'\x03');check(s,0x40c00800,72024848,'2af64aa7')
  copy(s,0x40c00800,0x8a000000,72024848)
  check(s,0x8a000000,72024848,'2af64aa7')
  reset(s,b'reset\r')
  check(s,0x8a000000,72024848,'2af64aa7')
  check(s,0x86000000,65526320,'b5f7ae2d')
  s.write(b'fastboot usb 1\r');read(s,3)
elif mode=='final':
 m=json.loads((root/'transfer.json').read_text());p=root/'first-firmware.bin'
 download(p,m['sha256'])
 with port() as s:
  cmd(s,b'\x03');check(s,0x40c00800,m['bytes'],m['crc32'])
  check(s,0x8a000000,72024848,'2af64aa7');check(s,0x86000000,65526320,'b5f7ae2d')
  copy(s,0x8a000000,0x90000000,72024848);check(s,0x90000000,72024848,'2af64aa7')
  copy(s,0x40c00800,0x80000000,0x6000000);check(s,0x80000000,166189616,'b20f998f')
  copy(s,0x46c00800,0x40400000,m['firmware_bytes']);check(s,0x40400000,m['firmware_bytes'],m['firmware_crc32'])
  assert b'edfe0dd0' in cmd(s,b'md.l 48300000 1\r').lower()
  s.write(b'booti 40400000 - 48300000\r');read(s,20)
elif mode=='probe':
 with port() as s:
  s.write(b'\r');assert b'nsh>' in read(s,2)
  s.write(b'k7voice asr-model &\r');read(s,45)
elif mode=='observe':
 with port() as s:read(s,45)
else:raise ValueError(mode)
