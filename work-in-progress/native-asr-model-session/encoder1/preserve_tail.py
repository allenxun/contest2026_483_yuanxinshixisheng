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

manifest=json.loads((root/'recovery-manifest.json').read_text())
with port() as s:
    cmd(s,b'\x03')
    raw=cmd(s,b'crc32 41c00800 3e7da30\r',20)
    assert re.search(rb'==>\s+'+manifest['tail_crc32'].encode()+rb'\b',raw)
    for offset in range(0,65526320,0x400000):
        count=min(0x400000,65526320-offset)
        cmd(s,('cp.b %x %x %x\r'%(0x41c00800+offset,0x86000000+offset,count)).encode())
    raw=cmd(s,b'crc32 86000000 3e7da30\r',20)
    assert re.search(rb'==>\s+'+manifest['tail_crc32'].encode()+rb'\b',raw)
    s.write(b'fastboot usb 1\r');read(s,3)
