"""Verify actual CLI parsing and binary writes through a host pseudo terminal."""
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import tempfile
import time
import tty

here = Path(__file__).resolve().parent
results = []
with tempfile.TemporaryDirectory(prefix='protocol-test-', dir=here) as folder:
    root = Path(folder)
    (root / 'nuttx').mkdir()
    (root / 'nuttx/config.h').write_text('')
    master, slave = pty.openpty()
    tty.setraw(slave)
    port = root / 'serial'
    port.symlink_to(os.ttyname(slave))
    exe = root / 'gimbal'
    subprocess.run(['gcc', '-std=c11', '-D_POSIX_C_SOURCE=200809L',
                    '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(root),
                    f'-DGIMBAL_PORT="{port}"', str(here / 'gimbal_main.c'),
                    '-o', str(exe)], check=True)

    def run(args, expected=b'', code=0):
        start = time.monotonic()
        p = subprocess.run([str(exe), *args], capture_output=True, timeout=8)
        data = bytearray()
        while select.select([master], [], [], .03)[0]:
            data.extend(os.read(master, 8192))
        assert p.returncode == code, (args, p.returncode, p.stderr)
        assert data == expected, (args, data.hex(), expected.hex())
        results.append(dict(args=args, passed=True, bytes=len(data),
                            seconds=round(time.monotonic()-start, 3),
                            stdout=p.stdout.decode(), stderr=p.stderr.decode()))
        return p.stdout

    def pair(x, y):
        return b'\x55\xaa\x00'+struct.pack('<h', x)+b'\x00\xfa' + \
               b'\x55\xaa\xff'+struct.pack('<h', y)+b'\x00\xfa'

    assert run(['frame', '10', '-10']) == \
        b'55 AA 00 0A 00 00 FA\n55 AA FF F6 FF 00 FA\n'
    run(['set', '10', '-10', '40'], pair(10, -10)*2)
    run(['set', '-250', '200', '20'], pair(-250, 200))
    run(['zero'], pair(0, 0)*15)
    points = [(0,0), (2,0), (-2,0), (0,0), (0,2), (0,-2), (0,0)]
    run(['test', '2'], b''.join(pair(x,y)*25 for x,y in points))
    for args in [['set','251','0'], ['set','0','-201'],
                 ['set','999999999999999999999','0'], ['set','10x','0'],
                 ['set','1','2','0'], ['test','51']]:
        run(args, code=1)
    port.unlink()
    run(['zero'], code=1)
    os.close(master)
    os.close(slave)
(here / 'protocol-tests.json').write_text(json.dumps(results, indent=2))
print(f'PASS: {len(results)} CLI/protocol/PTY checks; no hardware accessed.')
