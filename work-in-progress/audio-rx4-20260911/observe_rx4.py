"""Run bounded RX4 routing A/B checks on the live board and save raw evidence."""
import json
import re
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent
STAMP = time.strftime('%Y%m%d-%H%M%S')
LOG_PATH = ROOT / ('rx4-smoke-' + STAMP + '.log')
RESULT_PATH = ROOT / ('rx4-smoke-' + STAMP + '.json')


def read_until_prompt(port, seconds):
    data = bytearray()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        data.extend(port.read(8192))
        if re.search(rb'nsh>\s*(?:\x1b\[K)?$', data):
            break
    with LOG_PATH.open('ab') as output:
        output.write(data)
    print(data.decode(errors='replace'), flush=True)
    return bytes(data)


def parse(command, data):
    pio = re.search(rb'SOUND pio=(-?\d+) frames=(\d+).*?stop=(-?\d+) held=(\d+)', data)
    pcm = re.search(rb'left_nonzero=(\d+).*?right_nonzero=(\d+)', data)
    route = re.search(rb'SOUND rx4 lanes=(\d+) route_all=(\d+)', data)
    return {
        'command': command,
        'requested_frames': 3200,
        'pio_result': int(pio.group(1)) if pio else None,
        'captured_frames': int(pio.group(2)) if pio else None,
        'stop_result': int(pio.group(3)) if pio else None,
        'held': int(pio.group(4)) if pio else None,
        'left_nonzero': int(pcm.group(1)) if pcm else None,
        'right_nonzero': int(pcm.group(2)) if pcm else None,
        'rx_lanes': int(route.group(1)) if route else None,
        'route_all': bool(int(route.group(2))) if route else None,
        'terminal_result_ok': b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in data,
    }


port = serial.Serial(port=None, baudrate=1500000, timeout=.02, write_timeout=2)
port.dtr = False
port.rts = False
port.port = '/dev/ttyUSB0'
port.open()
results = []
try:
    port.write(b'\r')
    boot = read_until_prompt(port, 20)
    assert b'nsh>' in boot, 'Missing NSH prompt'
    for command in ('k7sound capture-pga24-rx4 3200',
                    'k7sound capture-pga24-rx4-all 3200'):
        with LOG_PATH.open('ab') as output:
            output.write(('\nCOMMAND ' + command + '\n').encode())
        port.write(command.encode() + b'\r')
        results.append(parse(command, read_until_prompt(port, 20)))
finally:
    port.close()

report = {
    'revision': 'audio-rx4-20260911',
    'hardware_tested': True,
    'raw_log': LOG_PATH.name,
    'results': results,
}
RESULT_PATH.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report), flush=True)
