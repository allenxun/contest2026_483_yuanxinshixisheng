import serial,time
s=serial.Serial('/dev/ttyUSB0',1500000,timeout=.1,write_timeout=2)
try:
    s.reset_input_buffer()
    for cmd,wait in [('k7host start',3),('k7host camera',8),('k7host probe',8),('k7host linkvideo &',3)]:
        s.write(cmd.encode()+b'\r');s.flush();end=time.monotonic()+wait;b=bytearray()
        while time.monotonic()<end:b.extend(s.read(8192))
        print('---',cmd,'---');print(b.decode(errors='replace'))
finally:s.close()
