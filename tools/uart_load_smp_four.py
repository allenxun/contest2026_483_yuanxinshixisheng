#!/usr/bin/env python3
"""Load the verified K7 image into RAM using U-Boot mw.q, with CRC gates."""
import argparse
import hashlib
from pathlib import Path
import re
import sys
import time
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "无线适配_2026-09-08/tools/pydeps"))
import serial

from verify_smp_four_image import verify

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('build', type=Path)
p.add_argument('--log', type=Path, required=True)
p.add_argument('--stage-only', action='store_true')
p.add_argument('--port', default='COM8')
a = p.parse_args()
build = a.build.resolve()
result = verify(build)
payload = (build / 'nuttx.bin').read_bytes()
# Immutable previous image used only for verified RAM block reuse. Relocated
# byte-identical blocks need not be retransmitted over the serial console.
previous_build = build.parent / 'emmc-vfs-20260910'
import json
previous_report = json.loads((Path(__file__).resolve().parents[1] / 'evidence/build/emmc-vfs-20260910/verification.json').read_text())
for name, item in previous_report['artifacts'].items():
    data = (previous_build / name).read_bytes()
    assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
previous = (previous_build / 'nuttx.bin').read_bytes()
snapshot_base = 0x51000000
assert snapshot_base + len(previous) < 0x51400000
reuse = {offset: previous.find(payload[offset:offset+4096])
         for offset in range(0, len(payload), 4096)}
base = 0x40400000
assert result['entry'] == hex(base)
assert 0 < len(payload) < 0x800000 and len(payload) % 8 == 0
print('IMAGE', len(payload), hashlib.sha256(payload).hexdigest(), flush=True)
assert build.name == 'smp-four-20260910'
fwdir = Path(__file__).resolve().parents[2] / '无线适配_2026-09-08/official-linux-20260320/source/external/rkwifibt/firmware/seekwave/ea6x21qx'
regions = [('openvela', base, payload)]
for name, address, size, digest in [
    ('SWT6621S_DRAM_SDIO.bin', 0x50000000, 193224, '7ddaae63b3281a4127565b2a7306fc74f8e5c7e88343a43c56a17d05a27d2b4b'),
    ('SWT6621S_IRAM_SDIO.bin', 0x50100000, 356616, '07d316bbf4dd18cc95671366c5001560f272026454fef1f6e134eb197189a169')]:
    data = (fwdir / name).read_bytes()
    assert len(data) == size and hashlib.sha256(data).hexdigest() == digest
    assert len(data) % 8 == 0 and address + size < 0x50200000
    regions.append((name, address, data))
nv = (fwdir / 'sv6160lite.nvbin').read_bytes()
assert len(nv) == 37 and hashlib.sha256(nv).hexdigest() == '1bb53545c5d67500c6141353b7ba8e2c8cb4b8b61d2f0835eec218f7a37efd44'
regions.append(('Bluetooth NVDS', 0x50180000, nv + b'\0' * 3))
calib = (fwdir / 'SWT6621S_SEEKWAVE_R00001.bin').read_bytes()
assert len(calib) == 2372 and hashlib.sha256(calib).hexdigest() == 'b20c04399d69f067d28bb07c24d3c2b1dca795f44e617a83cf6d254ef8715010'
regions.append(('Wi-Fi calibration', 0x50190000, calib + b'\0' * 4))
for i, (_, start, data) in enumerate(regions):
    for _, other, payload2 in regions[i+1:]:
        assert start+len(data) <= other or other+len(payload2) <= start

s = serial.Serial(port=None, baudrate=1500000, timeout=0.01,
                  write_timeout=3, rtscts=False,
                  dsrdtr=False, xonxoff=False)
s.dtr = False
s.rts = False
s.port = a.port
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
    # Separate RAM snapshot prevents destination writes from overwriting later
    # copy sources. Every reused block is CRC-checked both before and after.
    command(f'cp.b 40400000 {snapshot_base:x} {len(previous):x}')
    started = time.monotonic()
    for region_name, base, payload in regions:
        print('STAGE', region_name, hex(base), len(payload), flush=True)
        for offset in range(0, len(payload), 4096):
            chunk = payload[offset:offset+4096]
            if not crc_ok(base + offset, chunk):
                source_offset = reuse.get(offset, -1) if region_name == 'openvela' else -1
                if source_offset >= 0 and crc_ok(snapshot_base + source_offset, chunk):
                    command(f'cp.b {snapshot_base+source_offset:x} {base+offset:x} {len(chunk):x}')
                    if crc_ok(base + offset, chunk):
                        print('RAM REUSE VERIFIED', offset, flush=True)
                        continue
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
    print('PASS: FULL IMAGE, TWO FIRMWARE CRCs AND DTB VERIFIED', flush=True)
    if not a.stage_only:
        out = command('booti 40400000 - 48300000', timeout=25, prompt=rb'(?:\r?\n)nsh> ')
        print(out.decode(errors='replace'), flush=True)
        print('PASS: REAL K7 NSH', flush=True)






