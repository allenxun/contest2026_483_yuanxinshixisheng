"""Bounded true-board check of the vendor-style RX DMA request gate."""
import json
import re
import time
from pathlib import Path

import serial

root = Path(__file__).resolve().parent
stamp = time.strftime('%Y%m%d-%H%M%S')
log_path = root / ('rde-smoke-' + stamp + '.log')
result_path = root / ('rde-smoke-' + stamp + '.json')
port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()

def read_prompt(seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
            break
    with log_path.open('ab') as output:
        output.write(data)
    print(data.decode(errors='replace'), flush=True)
    return bytes(data)

try:
    port.write(b'\r')
    boot = read_prompt(15)
    assert b'nsh>' in boot, 'Missing NSH prompt'
    port.write(b'k7sound capture-pga24-rde 3200\r')
    data = read_prompt(15)
finally:
    port.close()

pio = re.search(rb'SOUND pio=(-?\d+) frames=(\d+).*?stop=(-?\d+) held=(\d+)', data)
dma = re.search(rb'SOUND dma_request active=([0-9a-fA-F]{8}) restore=(-?\d+)', data)
pcm = re.search(rb'left_nonzero=(\d+).*?right_nonzero=(\d+)', data)
result = {
    'requested_frames': 3200,
    'pio_result': int(pio.group(1)) if pio else None,
    'captured_frames': int(pio.group(2)) if pio else None,
    'stop_result': int(pio.group(3)) if pio else None,
    'held': int(pio.group(4)) if pio else None,
    'active_dmacr': dma.group(1).decode().lower() if dma else None,
    'dma_restore_result': int(dma.group(2)) if dma else None,
    'left_nonzero': int(pcm.group(1)) if pcm else None,
    'right_nonzero': int(pcm.group(2)) if pcm else None,
    'terminal_result_ok': b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in data,
    'hardware_tested': True,
    'raw_log': log_path.name,
}
result_path.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
