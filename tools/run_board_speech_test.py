"""Explicit already-running board commands, without reboot or Wi-Fi changes."""
import argparse,subprocess,time
from cloud_radio_stage_audit import remote,ROOT
p=argparse.ArgumentParser();p.add_argument('mode',choices=['status','tts','asr']);args=p.parse_args()
cmd={'status':'k7cloud radio-status','tts':'k7cloud tts-test 10.3.1.125','asr':'k7cloud asr-live 10.3.1.125'}[args.mode]
code=r'''
import serial,time
with serial.Serial('/dev/ttyUSB0',1500000,timeout=.02,write_timeout=2) as s:
 s.dtr=False;s.rts=False
 for c in %r.encode()+b'\r':s.write(bytes([c]));s.flush();time.sleep(.004)
 out=bytearray();end=time.monotonic()+65
 while time.monotonic()<end:
  out.extend(s.read(8192))
  if b'nsh>' in out:break
 else:print('CONSOLE_TIMEOUT',flush=True)
 print(out.decode(errors='replace'),flush=True)
'''%cmd
try:result=remote(code)
except subprocess.CalledProcessError as e:result=e.output
path=ROOT/'evidence/board-speech-bridge-20260914'/(args.mode+'-'+time.strftime('%H%M%S')+'.log')
path.write_bytes(result);print(result.decode(errors='replace'))
