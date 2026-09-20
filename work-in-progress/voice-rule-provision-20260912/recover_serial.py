"""Stop the current NSH foreground command and capture the resulting prompt."""

import time

import serial


port = serial.Serial("/dev/ttyUSB0", 1500000, timeout=.05, write_timeout=2,
                     rtscts=False, dsrdtr=False, xonxoff=False)
port.dtr = False
port.rts = False
try:
    port.write(b"\x03\r")
    port.flush()
    deadline = time.monotonic() + 4
    data = bytearray()
    while time.monotonic() < deadline:
        block = port.read(8192)
        if block:
            data.extend(block)
finally:
    port.close()
print(data.decode("utf-8", errors="replace"))
