"""Run on Ubuntu after download ACK; CRC and relocate the fixed trace image.

Does not boot, restart, or write flash. Serial must still be in Fastboot.
Uses non-overlapping memcpy-sized chunks because SDK cp.b uses memcpy.
"""
import hashlib
import re
import time
import zlib
from pathlib import Path
import serial

IMAGE = Path('/home/swl/openvela/cmake_out/velavision_voice_ort_trace_20260911/nuttx.bin')
EXPECTED = '967bea4cef6b9bf220d019ed8c06bb424eb33c40ff3e0f13af8eb15de539cb4f'
SOURCE, TARGET = 0x40c00800, 0x40400000


def main():
    data = IMAGE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED
    assert 0 < len(data) < 0x07000000
    crc = '%08x' % (zlib.crc32(data) & 0xffffffff)
    root = Path('/home/swl/openvela/work/usb-fastboot-preflight-20260911')
    log = root / ('full-ram-verify-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
    s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
    s.dtr = False
    s.rts = False
    s.port = '/dev/ttyUSB0'
    with log.open('xb') as record, s:
        def command(value):
            s.write(value)
            s.flush()
            raw = bytearray()
            start = time.monotonic()
            while time.monotonic() - start < 8:
                raw.extend(s.read(4096))
                if re.search(rb'(?:^|\n)=> $', raw):
                    break
            record.write(raw)
            record.flush()
            print(raw.decode(errors='replace'), flush=True)
            if not re.search(rb'(?:^|\n)=> $', raw):
                raise RuntimeError('No prompt; stop')
            if b'Unknown command' in raw or b'Usage:' in raw:
                raise RuntimeError('Command rejected')
            return bytes(raw)

        command(b'\x03')
        def verify(address):
            raw = command(('crc32 %x %x\r' % (address, len(data))).encode())
            assert re.search(rb'==>\s+' + crc.encode() + rb'\b', raw), 'CRC mismatch'
        verify(SOURCE)
        for offset in range(0, len(data), 0x400000):
            count = min(0x400000, len(data) - offset)
            assert TARGET + offset + count <= SOURCE + offset
            command(('cp.b %x %x %x\r' % (SOURCE + offset, TARGET + offset, count)).encode())
        verify(TARGET)
        command(b'md.l 48300000 1\r')
        print('Full RAM image CRC passed; no boot performed', flush=True)


if __name__ == '__main__':
    main()
