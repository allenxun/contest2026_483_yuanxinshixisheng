import json,time,re,hashlib
from pathlib import Path
import serial
here=Path(__file__).resolve().parent
stamp=time.strftime('%Y%m%d-%H%M%S');path=here/('tts-smoke-'+stamp+'.log')
with path.open('xb') as log,serial.Serial('/dev/ttyUSB0',1500000,timeout=.03,write_timeout=2,exclusive=True) as port:
    port.dtr=port.rts=False
    def command(text,timeout):
        port.write(text.encode()+b'\r');port.flush();data=bytearray();end=time.monotonic()+timeout
        while time.monotonic()<end:
            block=port.read(8192)
            if block:log.write(block);log.flush();data.extend(block);print(block.decode(errors='replace'),end='',flush=True)
            if b'U-Boot SPL' in data or b'PANIC' in data:raise RuntimeError('Unexpected firmware restart/fault')
            if re.search(rb'nsh>\s*(?:\x1b\[K)?\s*$',data):return bytes(data)
        raise RuntimeError('Command timeout; no retry or restart sent')
    command('',5)
    before=command('k7mem status',5)
    start=time.monotonic();out=command('k7voice tts-smoke',180);elapsed=time.monotonic()-start
    after=command('k7mem status',5)
    passed=b'VOICE_TTS result=0' in out and b'SOUND result=0 codec_stop=0 platform_restore=0 i2c_restore=0' in out
(here/('tts-smoke-'+stamp+'.json')).write_text(json.dumps({'passed':passed,'seconds':elapsed,'log_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'human_audibility_confirmed':False},indent=2))
assert passed,'Real synthesis/playback failed; inspect retained log'
print('\nTTS real synthesis/playback returned success; human audibility pending')
