"""CRC-gated firmware-only RAM copy/boot; no reset or persistent writes."""
import hashlib
import json
import re
import time
from pathlib import Path
import serial

HERE = Path(__file__).resolve().parent
m = json.loads((HERE / 'package.json').read_text())
image = (HERE / 'speaker-csr.bin').read_bytes()
assert len(image) == m['bytes'] and hashlib.sha256(image).hexdigest() == m['sha256']
assert 0 < len(image) < 0x01000000 and m['flash_commands'] is False
log_path = HERE / ('ram-boot-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
with log_path.open('xb') as log, serial.Serial('/dev/ttyUSB0', 1500000,
        timeout=.02, write_timeout=2, rtscts=False, dsrdtr=False, xonxoff=False) as p:
    p.dtr = p.rts = False
    def receive(seconds, pattern):
        data = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            b = p.read(4096)
            data.extend(b)
            log.write(b)
            log.flush()
            if re.search(pattern, data):
                print(data.decode(errors='replace'), end='', flush=True)
                return bytes(data)
        raise RuntimeError('missing expected prompt; stopped')
    def command(s):
        p.write(s.encode() + b'\r')
        p.flush()
        b = receive(35, rb'(?:^|\n)=>\s*$')
        assert b'Unknown command' not in b and b'Usage:' not in b
        return b
    def crc(addr, n, expected):
        b = command('crc32 %x %x' % (addr, n))
        assert re.search(rb'==>\s+' + expected.encode() + rb'\b', b), hex(addr)
    def copy(src, dst):
        assert src + len(image) <= dst or dst + len(image) <= src
        for offset in range(0, len(image), 0x400000):
            n = min(0x400000, len(image) - offset)
            command('cp.b %x %x %x' % (src + offset, dst + offset, n))
    p.write(b'\x03\r')
    receive(6, rb'(?:^|\n)=>\s*$')
    crc(0x40c00800, len(image), m['crc32'])
    crc(0x80000000, 0x9e7da30, 'b20f998f')
    crc(0x90000000, 0x44b0310, '2af64aa7')
    copy(0x40c00800, 0x46000000)
    crc(0x46000000, len(image), m['crc32'])
    copy(0x46000000, 0x40400000)
    crc(0x40400000, len(image), m['crc32'])
    assert b'edfe0dd0' in command('md.l 48300000 1').lower()
    p.write(b'booti 40400000 - 48300000\r')
    p.flush()
    receive(35, rb'nsh>')
record = {'firmware_sha256': m['sha256'], 'ram_crc_passed': True,
          'encoder_crc_passed': True, 'decoder_crc_passed': True,
          'nsh_reached': True, 'audible_passed': False,
          'flash_commands': False, 'log': str(log_path)}
(HERE / 'boot-result.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record))
