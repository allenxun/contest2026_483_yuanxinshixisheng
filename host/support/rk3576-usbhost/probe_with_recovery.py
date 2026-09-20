"""Capture one explicit NSH command; intercept U-Boot if firmware reboots."""
import argparse, re, time
from pathlib import Path
import serial
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--send', required=True)
p.add_argument('--seconds', type=float, default=25)
p.add_argument('--log', type=Path, required=True)
a = p.parse_args()
s = serial.Serial(port=None, baudrate=1500000, timeout=0.03,
                  write_timeout=2, exclusive=True, rtscts=False,
                  dsrdtr=False, xonxoff=False)
s.dtr = False
s.rts = False
s.port = '/dev/ttyUSB0'
s.open()
with s, a.log.open('ab') as log:
    s.write(a.send.encode('ascii') + b'\r')
    s.flush()
    start = time.monotonic()
    boot = None
    last = 0
    output = b''
    while time.monotonic() - start < a.seconds:
        data = s.read(max(1, min(s.in_waiting, 8192)))
        if data:
            log.write(data)
            log.flush()
            print(data.decode(errors='replace'), end='', flush=True)
            output = (output + data)[-32768:]
            if boot is None and (b'U-Boot ' in output or b'Hit key to stop autoboot' in output):
                boot = time.monotonic()
            if boot is not None and re.search(rb'(?:\r?\n)=>\s*$', output):
                print('\nRECOVERY: U-Boot intercepted', flush=True)
                break
        now = time.monotonic()
        if boot is not None and now - boot < 12 and now - last > 0.1:
            s.write(b'\x03')
            last = now
