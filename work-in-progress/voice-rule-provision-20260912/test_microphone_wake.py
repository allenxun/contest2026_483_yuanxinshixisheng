"""One real microphone wake/scan trial; no password entry or connection."""
import re
import time
from pathlib import Path
import serial

here = Path(__file__).resolve().parent
log_path = here / ('mic-wake-scan-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
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
        last_rx = time.monotonic()
        refreshed_prompt = False
        while time.monotonic() < end:
            block = port.read(8192)
            data.extend(block)
            log.write(block)
            log.flush()
            if block:
                last_rx = time.monotonic()
                print(block.decode('utf-8', errors='replace'), end='', flush=True)
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$', data):
                return bytes(data)
            # These commands never read stdin. One blank line after their
            # result can recover a dropped console prompt, without retrying
            # a capture or issuing another device operation.
            if (not refreshed_prompt and time.monotonic() - last_rx > 2 and
                    (b'SOUND result=' in data or b'VOICE_FLOW wake_text=' in data)):
                port.write(b'\r')
                port.flush()
                refreshed_prompt = True
        raise RuntimeError('NSH prompt missing after ' + text)
    command('', 5)
    print('MIC_TEST starts_in=8; say wake phrase after tone', flush=True)
    time.sleep(8)
    command('k7sound tone-max', 10)
    command('k7sound capture-pga24-grouped 48000', 15)
    command('k7voice flow-mic-wake', 210)
print('\nMIC_WAKE_LOG=' + str(log_path), flush=True)
