"""Bounded speaker or fixed-ASR crosscheck; never records new microphone input."""
import re
import sys
import time
from pathlib import Path
import serial

commands = {'tone': 'k7sound tone-max', 'replay': 'k7sound replay-max',
            'fixed-asr': 'k7voice asr-model'}
command = commands[sys.argv[1]]
log_path = Path(__file__).resolve().parent / (
    'audio-crosscheck-' + sys.argv[1] + '-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
with log_path.open('xb') as log, serial.Serial(
        '/dev/ttyUSB0', 1500000, timeout=.02, write_timeout=2,
        rtscts=False, dsrdtr=False, xonxoff=False) as port:
    port.dtr = False
    port.rts = False
    port.write(b'\r')
    def receive(seconds):
        data = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            block = port.read(8192)
            data.extend(block)
            log.write(block)
            log.flush()
            if block:
                print(block.decode('utf-8', errors='replace'), end='', flush=True)
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$', data):
                return
        raise RuntimeError('NSH prompt missing; no further command')
    receive(5)
    port.write(command.encode('ascii') + b'\r')
    port.flush()
    receive(210 if sys.argv[1] == 'fixed-asr' else 15)
print('\nCROSSCHECK_LOG=' + str(log_path), flush=True)
