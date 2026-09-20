#!/usr/bin/env python3
"""Read a retained camera frame through NSH xd; verify with two identical reads."""
import argparse, hashlib, json, re, struct, time
from pathlib import Path
import serial
p=argparse.ArgumentParser()
p.add_argument('build',type=Path);p.add_argument('output',type=Path)
a=p.parse_args()
symbols={}
for line in (a.build/'System.map').read_text().splitlines():
    fields=line.split()
    if len(fields)==3 and fields[2] in ('g_frame','g_frame_len'):
        symbols[fields[2]]=int(fields[0],16)
assert len(symbols)==2
s=serial.Serial(port=None,baudrate=1500000,timeout=.005,write_timeout=2,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
log=a.output.with_suffix('.serial.log').open('wb')
def xd(addr,n):
    assert 0x40400000<=addr and addr+n<=0x48200000 and 0<n<=16
    for retry in range(4):
        s.write(f'xd {addr:x} {n}\r'.encode());s.flush()
        data=b'';end=time.monotonic()+1.0
        while time.monotonic()<end:
            block=s.read(4096)
            if block:
                data+=block;log.write(block)
                if re.search(rb'\r?\nnsh> ',data):break
        rows={}
        for line in data.splitlines():
            m=re.match(rb'^([0-9a-fA-F]{4}): (.{48})',line)
            if m:
                try: rows[int(m[1],16)]=bytes.fromhex(m[2].decode())
                except ValueError:pass
        out=b''.join(rows.get(i,b'') for i in range(0,n,16))
        if len(out)==n:return out
        s.write(b'\r');time.sleep(.03);s.read(4096)
    raise RuntimeError(f'incomplete memory read at {addr:x}')
try:
    address=struct.unpack('<Q',xd(symbols['g_frame'],8))[0]
    length=struct.unpack('<Q',xd(symbols['g_frame_len'],8))[0]
    assert 4<=length<=4*1024*1024 and 0x40400000<=address<address+length<=0x48200000
    print(f'FRAME address={address:x} bytes={length}',flush=True)
    copies=[]
    for iteration in range(2):
        frame=bytearray()
        for offset in range(0,length,16):
            frame+=xd(address+offset,min(16,length-offset))
            if offset%4096==0:print(f'pass={iteration+1} read={offset}/{length}',flush=True)
        copies.append(bytes(frame))
    assert copies[0]==copies[1], 'Two memory reads differ'
    assert copies[0].startswith(b'\xff\xd8') and copies[0].endswith(b'\xff\xd9')
    a.output.write_bytes(copies[0])
    result={'address':hex(address),'bytes':length,'sha256':hashlib.sha256(copies[0]).hexdigest(),'identical_reads':2}
    a.output.with_suffix('.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
finally:
    log.close();s.close()
