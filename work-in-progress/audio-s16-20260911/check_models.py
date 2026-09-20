"""Read-only check of the two retained ASR model ranges in U-Boot."""
import re
import time
from pathlib import Path

import serial

root = Path(__file__).resolve().parent
stamp = time.strftime('%Y%m%d-%H%M%S')
log = root / ('model-crc-' + stamp + '.log')

port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()

def check(address, size, expected):
    port.write(('crc32 %x %x\r' % (address, size)).encode())
    data = bytearray()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        data.extend(port.read(4096))
        if data.endswith(b'=> '):
            break
    with log.open('ab') as output:
        output.write(data)
    assert re.search(rb'==>\s+' + expected.encode() + rb'\b', data), data
    print('CRC PASS address=%#x bytes=%d value=%s' %
          (address, size, expected), flush=True)

try:
    check(0x86000000, 65526320, 'b5f7ae2d')
    check(0x8a000000, 72024848, '2af64aa7')
finally:
    port.close()
