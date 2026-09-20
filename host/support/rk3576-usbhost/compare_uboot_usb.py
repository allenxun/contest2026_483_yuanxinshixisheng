"""Compare known USB/clock/PHY registers before and after U-Boot usb start."""
from pathlib import Path
import json, re, time
import serial
work = Path('/home/swl/openvela/work/rk3576-usbhost')
addresses = sorted(set(
    [0x27200888,0x2720088c,0x27200890,0x27200a8c,0x27200a90,
     0x27220800,0x27220804,0x27220808,0x27220a00,0x27220a04,
     0x26020030,0x26020038,0x26030000,0x26030004,0x26030008,
     0x2603000c,0x26030010,0x26030014,0x26030080,
     0x2340c100,0x2340c104,0x2340c108,0x2340c10c,
     0x2340c110,0x2340c11c,0x2340c12c,0x2340c130,
     0x2340c200,0x2340c2c0,0x2340c630] +
    list(range(0x27200898,0x272008a8,4))))
s=serial.Serial(port=None,baudrate=1500000,timeout=.01,write_timeout=3,exclusive=True)
s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
with s, (work/'uboot-platform-compare.log').open('ab') as log:
    def command(cmd, seconds=3):
        s.write(cmd.encode()+b'\r');s.flush()
        out=b'';end=time.monotonic()+seconds
        while time.monotonic()<end:
            data=s.read(4096)
            if data:
                out+=data;log.write(data);log.flush()
                if re.search(rb'(?:\r?\n)=>\s*$',out):return out
        return out
    def snapshot():
        result={}
        for addr in addresses:
            for attempt in range(3):
                out=command(f'md.l {addr:x} 1')
                m=re.search(fr'{addr:08x}:\s*([0-9a-f]{{8}})'.encode(),out)
                if m:
                    result[f'{addr:08x}']=m[1].decode();break
            else:raise RuntimeError(f'Missing register {addr:x}: {out!r}')
        return result
    before=snapshot()
    (work/'uboot-platform-before.json').write_text(json.dumps(before,indent=2))
    out=command('usb start',25)
    print(out.decode(errors='replace'),flush=True)
    after=snapshot()
    (work/'uboot-platform-after.json').write_text(json.dumps(after,indent=2))
    diff={key:[before[key],after[key]] for key in before if before[key]!=after[key]}
    (work/'uboot-platform-diff.json').write_text(json.dumps(diff,indent=2))
    print(json.dumps(diff,indent=2),flush=True)
