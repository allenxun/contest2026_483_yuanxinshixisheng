"""Owned first USB experiment: enumerate, then separately read one new node."""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R/'evidence/usb-readonly-20260910'
sys.path.insert(0, str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
from verify_usb_readonly_image import verify

p = argparse.ArgumentParser()
p.add_argument('phase', choices=['enumerate', 'read'])
p.add_argument('--node')
a = p.parse_args()
verify(R/'artifacts/usb-readonly-20260910')
if a.phase == 'read':
    report = json.loads((E/'enumeration.json').read_text())
    assert report['passed'] and report['new_nodes'] == [a.node]
    assert re.fullmatch('/dev/sd[a-z]', a.node)
s = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=3)
s.dtr = False
s.rts = False
s.port = 'COM8'
prompt = rb'nsh>\s*(?:\x1b\[K)?$'

def capture(name, command, timeout=15):
    path = E/(name+'.bin')
    with path.open('xb') as f:
        s.write(command.encode('ascii')+b'\r')
        s.flush()
        raw = bytearray()
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            data = s.read(8192)
            f.write(data)
            raw.extend(data)
            if re.search(prompt, raw):
                return bytes(raw)
    # No task deletion, controller reset or speculative DMA cleanup.
    raise RuntimeError('Observation deadline; leave target task untouched: '+name)

def nodes(raw):
    assert b'USB_STORAGE command=list result=0 mount_attempted=0' in raw
    return sorted(set(m.decode() for m in re.findall(rb'USB_STORAGE node=(/dev/sd[a-z])\b', raw)))

with s:
    if a.phase == 'enumerate':
        before = capture('before', 'k7storage list')
        old = nodes(before)
        start = capture('start', 'k7storage start', 25)
        assert b'USB_STORAGE command=start result=0 mount_attempted=0' in start
        # Class registration is asynchronous. Preserve all waiter output.
        with (E/'enumeration-wait.bin').open('xb') as f:
            deadline = time.monotonic()+25
            while time.monotonic() < deadline:
                f.write(s.read(8192))
        after = capture('after', 'k7storage list')
        new = sorted(set(nodes(after))-set(old))
        result = dict(passed=len(new)==1, before=old, after=nodes(after), new_nodes=new,
                      media_written=False, mounted=False, identity_reviewed=False,
                      scope='Node enumeration only; physical identity requires log review',
                      hashes={n:hashlib.sha256((E/n).read_bytes()).hexdigest() for n in
                              ('before.bin','start.bin','enumeration-wait.bin','after.bin')})
        with (E/'enumeration.json').open('x') as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result))
    else:
        raw = capture('read', 'k7storage read '+a.node, 20)
        passed = (b'USB_STORAGE command=read result=0 mount_attempted=0' in raw and
                  b'readonly=1 lba=0 reads=2' in raw and b'repeated=1' in raw)
        print(json.dumps(dict(passed=passed, node=a.node, media_written=False)))
