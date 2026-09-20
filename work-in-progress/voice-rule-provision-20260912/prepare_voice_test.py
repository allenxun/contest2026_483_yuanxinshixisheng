"""Initialize the RAM voice test firmware without recording or submitting credentials."""
import re
import time
from pathlib import Path
import serial

here = Path(__file__).resolve().parent
log_path = here / ('voice-prepare-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
with log_path.open('xb') as log, serial.Serial(
        '/dev/ttyUSB0', 1500000, timeout=.02, write_timeout=2,
        rtscts=False, dsrdtr=False, xonxoff=False) as port:
    port.dtr = False
    port.rts = False
    def command(text, timeout):
        port.write(text.encode('ascii') + b'\r')
        port.flush()
        data = bytearray()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            block = port.read(8192)
            data.extend(block)
            log.write(block)
            log.flush()
            if block:
                print(block.decode('utf-8', errors='replace'), end='', flush=True)
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$', data):
                return bytes(data)
        raise RuntimeError('NSH prompt missing after ' + text)
    command('', 5)
    for text in ('k7radio sdio-boot', 'k7radio bt-host',
                 'k7radio wifi-service-start', 'k7voice probe'):
        result = command(text, 45)
        if b'command not found' in result or b'up_assert:' in result:
            raise RuntimeError('Startup command failed: ' + text)
print('\nPREPARE_LOG=' + str(log_path), flush=True)
