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

assert mode in ('part1','part2')
manifest=json.loads((root/'transfer-manifest.json').read_text())
index=0 if mode=='part1' else 1
item=manifest['transfers'][index]
assert item['file'] in ('encoder-part1.bin','encoder-part2-firmware.bin')
image=root/item['file'];data=image.read_bytes()
assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
assert len(data)<=0x07000000 and manifest['encoder_bytes']==166189616
subprocess.run([sys.executable,'/home/swl/openvela/work/usb-fastboot-preflight-20260911/fastboot_ram_download.py',str(image),'--sha256',item['sha256'],'--vid','0x18d1','--pid','0x4d00','--serial','f71a9d152132db55','--audited-running-buffer','0x40c00800:0x07000000','--result',str(root/(mode+'-usb-'+stamp+'.json'))],check=True,timeout=90)
with port() as s:
    cmd(s,b'\x03')
    def check(address,count,crc):
        raw=cmd(s,('crc32 %x %x\r'%(address,count)).encode(),20)
        assert re.search(rb'==>\s+'+crc.encode()+rb'\b',raw),'RAM CRC mismatch'
    def copy(source,target,count):
        for offset in range(0,count,0x400000):
            n=min(0x400000,count-offset)
            assert target+offset+n<=source+offset or source+offset+n<=target+offset
            cmd(s,('cp.b %x %x %x\r'%(source+offset,target+offset,n)).encode())
    check(0x40c00800,len(data),item['crc32'])
    if index==0:
        assert len(data)==0x6000000
        copy(0x40c00800,0x80000000,len(data));check(0x80000000,len(data),item['crc32'])
        print('Encoder first segment verified; remain at U-Boot',flush=True)
    else:
        check(0x80000000,0x6000000,manifest['transfers'][0]['crc32'])
        copy(0x41c00800,0x86000000,166189616-0x6000000)
        check(0x80000000,166189616,manifest['encoder_crc32'])
        count=manifest['firmware_bytes'];assert 0<count<0x1000000
        copy(0x40c00800,0x40400000,count);check(0x40400000,count,manifest['firmware_crc32'])
        raw=cmd(s,b'md.l 48300000 1\r');assert b'edfe0dd0' in raw.lower()
        s.write(b'booti 40400000 - 48300000\r');read(s,20)
