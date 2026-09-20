"""Bounded explicit RAM-only decoder test on Ubuntu; no flash commands."""
import hashlib, json, re, subprocess, sys, time, zlib
from pathlib import Path
import serial

root=Path(__file__).resolve().parent
mode=sys.argv[1]
stamp=time.strftime('%Y%m%d-%H%M%S')
log=(root/(mode+'-'+stamp+'.log')).open('xb')
def port():
    s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
    s.dtr=False; s.rts=False; s.port='/dev/ttyUSB0'; s.open(); return s
def read(s, seconds, prompt=None):
    raw=bytearray(); end=time.monotonic()+seconds
    while time.monotonic()<end:
        raw.extend(s.read(4096))
        if prompt and re.search(prompt,raw): break
    log.write(raw);log.flush();print(raw.decode(errors='replace'),flush=True)
    return bytes(raw)
def cmd(s,value,seconds=12):
    s.write(value);s.flush();raw=read(s,seconds,rb'(?:^|\n)=> $')
    assert re.search(rb'(?:^|\n)=> $',raw),'Missing U-Boot prompt'
    assert b'Unknown command' not in raw and b'Usage:' not in raw
    return raw

image=root/'encoder-first-firmware.bin';expected='9951c2742be81d6fad8ed3a432c2d294271748f2cfcbb9241235bc8369f5071b'
data=image.read_bytes();assert len(data)==115348800 and hashlib.sha256(data).hexdigest()==expected
subprocess.run([sys.executable,'/home/swl/openvela/work/usb-fastboot-preflight-20260911/fastboot_ram_download.py',str(image),'--sha256',expected,'--vid','0x18d1','--pid','0x4d00','--serial','f71a9d152132db55','--audited-running-buffer','0x40c00800:0x07000000','--result',str(root/('recover-usb-'+stamp+'.json'))],check=True,timeout=90)
with port() as s:
    cmd(s,b'\x03')
    def check(addr,n,crc):
        raw=cmd(s,('crc32 %x %x\r'%(addr,n)).encode(),20)
        assert re.search(rb'==>\s+'+crc.encode()+rb'\b',raw),'RAM CRC mismatch'
    def copy(src,dst,n):
        assert src+n<=dst or dst+n<=src
        for offset in range(0,n,0x400000):
            cmd(s,('cp.b %x %x %x\r'%(src+offset,dst+offset,min(0x400000,n-offset))).encode())
    check(0x40c00800,len(data),'d57c3a92');check(0x86000000,65526320,'b5f7ae2d')
    copy(0x40c00800,0x80000000,0x6000000)
    check(0x80000000,166189616,'b20f998f')
    copy(0x46c00800,0x40400000,14685504);check(0x40400000,14685504,'0600d0fe')
    raw=cmd(s,b'md.l 48300000 1\r');assert b'edfe0dd0' in raw.lower()
    s.write(b'booti 40400000 - 48300000\r');read(s,20)
