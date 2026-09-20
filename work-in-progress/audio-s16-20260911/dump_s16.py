"""Read back the retained diagnostic capture and summarize raw word cadence."""
import collections
import json
import re
import time
from pathlib import Path

import serial

root = Path(__file__).resolve().parent
stamp = time.strftime('%Y%m%d-%H%M%S')
raw_path = root / ('s16-dump-' + stamp + '.log')
result_path = root / ('s16-dump-' + stamp + '.json')
port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()
try:
    port.write(b'k7sound dump\r')
    data = bytearray()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        data.extend(port.read(32768))
        if b'SOUND_PCM_END' in data and re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
            break
finally:
    port.close()
raw_path.write_bytes(data)
header = re.search(rb'SOUND_PCM frames=(\d+) rate=(\d+) channels=(\d+) bits=(\d+)', data)
assert header, 'Missing dump header'
words = []
for line in data.splitlines():
    if line.startswith(b'PCM '):
        words.extend(int(value, 16) for value in line.split()[2:])
frames, rate, channels, bits = [int(value) for value in header.groups()]
assert len(words) == frames * channels
residue = []
for modulo in range(8):
    lane = words[modulo::8]
    residue.append({'modulo': modulo, 'count': len(lane),
                    'nonzero': sum(value != 0 for value in lane),
                    'unique_first_128': len(set(lane[:128]))})
result = {
    'frames': frames, 'rate': rate, 'channels': channels, 'bits': bits,
    'words': len(words), 'first_64': ['%08x' % value for value in words[:64]],
    'residue8': residue,
    'most_common': [('%08x' % value, count)
                    for value, count in collections.Counter(words).most_common(12)],
}
result_path.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
