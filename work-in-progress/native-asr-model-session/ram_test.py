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
if mode=='reenter':
    with port() as s:
        cmd(s,b'\x03')
        s.write(b'fastboot usb 1\r');read(s,5)
elif mode in ('enter','resetenter'):
    with port() as s:
        if mode=='enter':
            s.write(b'\r'); raw=read(s,3)
            assert b'nsh>' in raw,'Require running NSH before reboot'
            s.write(b'reboot\r')
        else:
            cmd(s,b'\x03');s.write(b'reset\r')
        end=time.monotonic()+15;raw=bytearray(); seen=False
        while time.monotonic()<end:
            chunk=s.read(4096);raw.extend(chunk);log.write(chunk);log.flush()
            if b'U-Boot 2017' in raw: seen=True
            if seen:s.write(b'\x03');time.sleep(.05)
            if re.search(rb'(?:^|\n)=> $',raw):break
        assert re.search(rb'(?:^|\n)=> $',raw),'Autoboot was not interrupted'
        s.write(b'fastboot usb 1\r');read(s,2)
elif mode=='bundle':
    image=root/'decoder-firmware-bundle.bin'
    expected='25c23c987977d1a5a6956a57f2c40c6931c2af5d36b201ec27267f7e45de98a9'
    data=image.read_bytes();assert hashlib.sha256(data).hexdigest()==expected
    assert len(data)==88802064 and len(data)<0x07000000
    downloader='/home/swl/openvela/work/usb-fastboot-preflight-20260911/fastboot_ram_download.py'
    subprocess.run([sys.executable,downloader,str(image),'--sha256',expected,
        '--vid','0x18d1','--pid','0x4d00','--serial','f71a9d152132db55',
        '--audited-running-buffer','0x40c00800:0x07000000',
        '--result',str(root/('bundle-usb-'+stamp+'.json'))],check=True,timeout=90)
    with port() as s:
        cmd(s,b'\x03')
        def crc_check(address,count,crc):
            raw=cmd(s,('crc32 %x %x\r'%(address,count)).encode())
            assert re.search(rb'==>\s+'+crc.encode()+rb'\b',raw),'RAM CRC mismatch'
        crc_check(0x40c00800,len(data),'611d9c62')
        # Copy decoder first; firmware relocation may overwrite bundle source.
        for source,target,size,crc in [(0x41c00800,0x80000000,72024848,'2af64aa7'),
                                      (0x40c00800,0x40400000,14685504,'605ed5e2')]:
            crc_check(source,size,crc)
            for offset in range(0,size,0x400000):
                count=min(0x400000,size-offset)
                assert target+offset+count<=source+offset or source+offset+count<=target+offset
                cmd(s,('cp.b %x %x %x\r'%(source+offset,target+offset,count)).encode())
            crc_check(target,size,crc)
        raw=cmd(s,b'md.l 48300000 1\r');assert b'edfe0dd0' in raw.lower()
        s.write(b'booti 40400000 - 48300000\r');read(s,20)
elif mode in ('model','firmware'):
    model=mode=='model'
    image=root/'decoder.ort' if model else Path('/home/swl/openvela/cmake_out/velavision_voice_asr_model_20260911/nuttx.bin')
    expected='0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14' if model else 'c8f58b202842032ea155d877fb91003df70c2480039b93851a2e10c98c9da9ca'
    data=image.read_bytes();assert hashlib.sha256(data).hexdigest()==expected
    crc=('%08x'%(zlib.crc32(data)&0xffffffff)).encode()
    downloader='/home/swl/openvela/work/usb-fastboot-preflight-20260911/fastboot_ram_download.py'
    subprocess.run([sys.executable,downloader,str(image),'--sha256',expected,
        '--vid','0x18d1','--pid','0x4d00',
        '--serial','f71a9d152132db55','--audited-running-buffer','0x40c00800:0x07000000',
        '--result',str(root/(mode+'-usb-'+stamp+'.json'))],check=True,timeout=90)
    with port() as s:
        cmd(s,b'\x03')
        def check(address):
            raw=cmd(s,('crc32 %x %x\r'%(address,len(data))).encode())
            assert re.search(rb'==>\s+'+crc+rb'\b',raw),'RAM CRC mismatch'
        check(0x40c00800)
        target=0x80000000 if model else 0x40400000
        for offset in range(0,len(data),0x400000):
            count=min(0x400000,len(data)-offset)
            cmd(s,('cp.b %x %x %x\r'%(0x40c00800+offset,target+offset,count)).encode())
        check(target)
        if model:s.write(b'fastboot usb 1\r');read(s,2)
        else:
            raw=cmd(s,b'md.l 48300000 1\r');assert b'edfe0dd0' in raw.lower()
            s.write(b'booti 40400000 - 48300000\r');read(s,20)
elif mode=='probe':
    with port() as s:
        s.write(b'\r');raw=read(s,2);assert b'nsh>' in raw
        s.write(b'k7voice asr-model &\r');read(s,45)
else:raise ValueError(mode)
