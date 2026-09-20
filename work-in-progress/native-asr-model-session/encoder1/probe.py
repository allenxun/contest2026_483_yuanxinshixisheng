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

assert mode=='probe'
with port() as s:
    s.write(b'\r');raw=read(s,2);assert b'nsh>' in raw
    s.write(b'k7voice asr-model &\r');read(s,45)
