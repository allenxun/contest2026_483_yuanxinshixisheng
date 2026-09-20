"""Bounded reboot after a passed minimal SMP diagnostic; always save output."""
import argparse,json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--revision',required=True,choices=['smp-four-20260910','smp-cross-20260910','smp-eight-20260910'])
a=p.parse_args();e=R/'evidence'/a.revision
assert json.loads((e/('diagnostic-attempt04.json' if a.revision == 'smp-eight-20260910' else 'diagnostic.json')).read_text())['passed']
assert 'CONFIG_BOARDCTL_RESET=y' in (R/'artifacts'/a.revision/'.config').read_text().splitlines()
assert not (e/'software-reset.json').exists()
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';buf=bytearray();ok=False;start=time.monotonic()
try:
    with s:
        s.write(b'reboot\r');s.flush()
        while time.monotonic()-start<25:
            buf.extend(s.read(8192));s.write(b'\x03');s.flush()
            if re.search(rb'(?:\r?\n)=>\s*$',buf):ok=True;break
finally:
    (e/'software-reset.bin').write_bytes(buf)
    (e/'software-reset.json').write_text(json.dumps(dict(uboot_prompt=ok,elapsed=time.monotonic()-start,storage_writes=False)))
if not ok:raise RuntimeError('No U-Boot prompt; preserve evidence, no blind retry')
print('PASS: diagnostic software reset reached U-Boot')
