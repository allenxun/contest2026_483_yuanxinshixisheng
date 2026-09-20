"""Apply the user-selected runtime volume without rebooting K7."""
from pathlib import Path
from cloud_radio_stage_audit import remote

code = r'''
import serial,time,subprocess
owners=subprocess.run(['fuser','/dev/ttyUSB0'],capture_output=True,text=True)
if owners.stdout.strip():
    raise RuntimeError('Serial is still owned; refusing concurrent access')
s=serial.Serial(port=None,baudrate=1500000,timeout=0.2,exclusive=True)
s.rts=False;s.dtr=False;s.port='/dev/ttyUSB0';s.open()
try:
    s.write(b'\nk7sound speech-volume 10\n');s.flush()
    end=time.monotonic()+4
    data=bytearray()
    while time.monotonic()<end:data.extend(s.read(8192))
    text=data.decode(errors='replace')
    print(text)
    if 'SOUND speech_gain_db=10 cue_gain_db=24 next_playback=1' not in text:
        raise RuntimeError('Volume acknowledgement not received')
finally:s.close()
'''
data=remote(code)
out=Path(__file__).resolve().parents[1]/'evidence/stage-watch-20260916/speech-volume-10.log'
out.write_bytes(data)
print(data.decode(errors='replace'))
