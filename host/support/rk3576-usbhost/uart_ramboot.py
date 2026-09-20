#!/usr/bin/env python3
"""Load the verified K7 image into RAM using U-Boot mw.q, with CRC gates."""
import argparse
import hashlib
from pathlib import Path
import re
import sys
import time
import zlib
import serial

sys.path.insert(0, '/home/swl/openvela/work/rk3576-bringup')
from verify_image import verify

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('build', type=Path)
p.add_argument('--log', type=Path, required=True)
p.add_argument('--stage-only', action='store_true')
a = p.parse_args()
build = a.build.resolve()
result = verify(build)
payload = (build / 'nuttx.bin').read_bytes()
base = 0x40400000
assert result['entry'] == hex(base)
assert 0 < len(payload) < 0x800000 and len(payload) % 8 == 0
print('IMAGE', len(payload), hashlib.sha256(payload).hexdigest(), flush=True)
s = serial.Serial(port=None, baudrate=1500000, timeout=0.01,
                  write_timeout=3, exclusive=True, rtscts=False,
                  dsrdtr=False, xonxoff=False)
s.dtr = False
s.rts = False
s.port = '/dev/ttyUSB0'
s.open()
with s, a.log.open('ab') as log:
    def command(cmd, timeout=4, prompt=rb'(?:\r?\n)=>\s*$'):
        raw = cmd.encode('ascii') + b'\r'
        # Bounded lines, paced bytes: do not overrun U-Boot's UART input FIFO.
        for pos in range(0, len(raw), 32):
            s.write(raw[pos:pos+32])
            time.sleep(0.001)
        s.flush()
        output = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = s.read(8192)
            if data:
                output.extend(data)
                log.write(data)
                if re.search(prompt, output):
                    return bytes(output)
        log.flush()
        raise RuntimeError('Prompt missing: ' + cmd[:80] + '\n' + output.decode(errors='replace')[-1500:])

    def crc_ok(address, data):
        out = command(f'crc32 {address:x} {len(data):x}')
        match = re.search(rb'==>\s*([0-9a-fA-F]{8})', out)
        return match is not None and int(match[1], 16) == zlib.crc32(data)

    # A short read avoids the CH340 burst loss seen with U-Boot's version
    # banner. Both the U-Boot prompt and known DTB signature are required.
    out = command('md.l 48300000 1')
    assert re.search(rb'48300000:\s+edfe0dd0\b', out), out
    started = time.monotonic()
    for offset in range(0, len(payload), 4096):
        chunk = payload[offset:offset+4096]
        if not crc_ok(base + offset, chunk):
            for attempt in range(3):
                commands = []
                pos = 0
                while pos < len(chunk):
                    value = int.from_bytes(chunk[pos:pos+8], 'little')
                    count = 1
                    while pos + (count+1)*8 <= len(chunk) and chunk[pos+count*8:pos+(count+1)*8] == chunk[pos:pos+8]:
                        count += 1
                    address = base + offset + pos
                    assert base <= address and address + count*8 <= base + len(payload)
                    commands.append(f'mw.q {address:x} {value:x} {count:x}')
                    pos += count * 8
                line = ''
                for cmd in commands:
                    if len(line) + len(cmd) + 1 > 700:
                        out = command(line)
                        if b'Unknown command' in out or b'Usage:' in out:
                            raise RuntimeError(out.decode(errors='replace'))
                        line = ''
                    line += (';' if line else '') + cmd
                if line:
                    command(line)
                if crc_ok(base + offset, chunk):
                    break
                print('RETRY', hex(base+offset), attempt+1, flush=True)
            else:
                raise RuntimeError('Chunk CRC failed; boot prevented')
        log.flush()
        print(f'CRC VERIFIED {offset+len(chunk)}/{len(payload)} ({time.monotonic()-started:.1f}s)', flush=True)
    assert crc_ok(base, payload), 'Full CRC failed; boot prevented'
    dtb = command('md.l 48300000 1')
    assert re.search(rb'48300000:\s+edfe0dd0\b', dtb), dtb
    print('PASS: FULL IMAGE CRC AND DTB VERIFIED', flush=True)
    if not a.stage_only:
        out = command('booti 40400000 - 48300000', timeout=25, prompt=rb'(?:\r?\n)nsh> ')
        print(out.decode(errors='replace'), flush=True)
        print('PASS: REAL K7 NSH', flush=True)
