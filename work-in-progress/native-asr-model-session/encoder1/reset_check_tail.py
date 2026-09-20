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

with port() as s:
    cmd(s,b'\x03')
    before=cmd(s,b'crc32 86000000 3e7da30\r',20)
    s.write(b'reset\r');end=time.monotonic()+15;raw=bytearray();seen=False
    while time.monotonic()<end:
        chunk=s.read(4096);raw.extend(chunk);log.write(chunk);log.flush()
        if b'U-Boot 2017' in raw:seen=True
        if seen:s.write(b'\x03');time.sleep(.05)
        if re.search(rb'(?:^|\n)=> $',raw):break
    assert re.search(rb'(?:^|\n)=> $',raw)
    after=cmd(s,b'crc32 86000000 3e7da30\r',20)
    result={'tail_before_valid':b'b5f7ae2d' in before,'tail_after_valid':b'b5f7ae2d' in after}
    (root/('usb-reset-'+stamp+'.json')).write_text(json.dumps(result,indent=2));print(result,flush=True)
    s.write(b'fastboot usb 1\r');read(s,3)
