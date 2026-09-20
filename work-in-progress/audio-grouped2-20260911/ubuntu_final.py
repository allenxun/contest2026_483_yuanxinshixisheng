"""Validate the staged TLS/ASR payload and RAM boot it through /dev/ttyUSB0.

The board must already be in U-Boot Fastboot after the audited USB downloader
has acknowledged the exact payload. No persistent-write command is available.
"""
import re
import sys
import time
from pathlib import Path

import serial


root = Path(__file__).resolve().parent
stamp = time.strftime('%Y%m%d-%H%M%S')
log_path = root / ('ubuntu-final-' + stamp + '.log')
log = log_path.open('xb')


def read(port, seconds, prompt=False):
    data = bytearray()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        data.extend(port.read(4096))
        if prompt and re.search(rb'(?:^|\n)=>\s*$', data):
            break
    log.write(data)
    log.flush()
    sys.stdout.write(data.decode(errors='replace'))
    sys.stdout.flush()
    return bytes(data)


def command(port, text, seconds=15):
    port.write(text.encode() + b'\r')
    port.flush()
    output = read(port, seconds, True)
    if not re.search(rb'(?:^|\n)=>\s*$', output):
        raise RuntimeError('U-Boot prompt missing after ' + text)
    if b'Unknown command' in output or b'Usage:' in output:
        raise RuntimeError('U-Boot rejected ' + text)
    return output


def check_crc(port, address, size, expected):
    output = command(port, f'crc32 {address:x} {size:x}', 30)
    if not re.search(rb'==>\s+' + expected.encode() + rb'\b', output):
        raise RuntimeError(f'CRC mismatch at {address:x}')


def copy(port, source, target, size):
    if not (source + size <= target or target + size <= source):
        raise RuntimeError('overlapping copy refused')
    for offset in range(0, size, 0x400000):
        count = min(0x400000, size - offset)
        command(port, f'cp.b {source + offset:x} {target + offset:x} {count:x}')


port = serial.Serial('/dev/ttyUSB0', 1500000, timeout=.02,
                     write_timeout=2, rtscts=False, dsrdtr=False,
                     xonxoff=False)
port.dtr = False
port.rts = False
try:
    port.write(b'\x03')
    output = read(port, 5, True)
    if not re.search(rb'(?:^|\n)=>\s*$', output):
        raise RuntimeError('Fastboot did not return to U-Boot')
    check_crc(port, 0x40C00800, 0x6E8E570, '73b7c4fe')
    check_crc(port, 0x90000000, 0x44B0310, '2af64aa7')
    check_crc(port, 0x86000000, 0x3E7DA30, 'b5f7ae2d')
    copy(port, 0x40C00800, 0x80000000, 0x6000000)
    check_crc(port, 0x80000000, 0x9E7DA30, 'b20f998f')
    copy(port, 0x46C00800, 0x40400000, 0xE8E570)
    check_crc(port, 0x40400000, 0xE8E570, 'c9b86048')
    if b'edfe0dd0' not in command(port, 'md.l 48300000 1').lower():
        raise RuntimeError('DTB magic mismatch')
    port.write(b'booti 40400000 - 48300000\r')
    boot = read(port, 30)
    if b'nsh>' not in boot:
        raise RuntimeError('RAM firmware did not reach NSH')
finally:
    port.close()
    log.close()
    print(f'K7_LOG={log_path}')
