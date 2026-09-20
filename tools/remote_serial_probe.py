import serial, sys, time
cmd = (sys.argv[1] if len(sys.argv) > 1 else '')
s = serial.Serial('/dev/ttyUSB0', 1500000, timeout=.1, write_timeout=2)
try:
    s.reset_input_buffer()
    if cmd == 'CTRL-C': s.write(bytes([3])); s.flush()
    elif cmd: s.write(cmd.encode() + b'\r'); s.flush()
    end = time.monotonic() + float(sys.argv[2] if len(sys.argv) > 2 else 8)
    b = bytearray()
    while time.monotonic() < end: b.extend(s.read(8192))
    sys.stdout.buffer.write(b)
finally: s.close()
