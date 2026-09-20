"""One bounded real CPU Add invocation after immutable CRC-verified boot."""
import sys,time,re,json
from pathlib import Path
from verify_voice_ort_trace_image import verify
R=Path(__file__).resolve().parents[1];E=R/'evidence/voice-ort-trace-20260911'
verify(R/'artifacts/voice-ort-trace-20260911')
assert '# CONFIG_NSH_DISABLEBG is not set' in (R/'artifacts/voice-ort-trace-20260911/.config').read_text()
from summarize_voice_trace import summarize
assert 'PASS: REAL K7 NSH' in (E/'ramload-progress.txt').read_text(encoding='utf-8-sig')
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
out=E/('add-run-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8'
rows=[]
with s:
 for name,command,limit,marker in [('before','free',5,b'Umem'),('add','k7voice ort-add &',60,b'ORT_ADD PASS values=11,22,33,44'),('after','free',5,b'Umem'),('tasks','ps',5,b'CPU7 IDLE')]:
  s.write(command.encode()+b'\r');s.flush();raw=bytearray();start=time.monotonic();prompt=False
  while time.monotonic()-start<limit:
   raw.extend(s.read(8192))
   if name == 'add':
    if marker in raw:break
   elif re.search(rb'nsh>\s*(?:\x1b\[K)?$',raw):prompt=True;break
  (out/(name+'.bin')).write_bytes(raw)
  row=dict(stage=name,seconds=time.monotonic()-start,prompt=prompt,passed=marker in raw and (name == 'add' or prompt))
  rows.append(row);(out/'result.json').write_text(json.dumps(dict(stages=rows,asr_tested=False,tts_tested=False),indent=2))
  print(json.dumps(row),flush=True);print(raw.decode(errors='replace'),flush=True)
  if name == 'add':
   (E/'trace-summary.json').write_text(json.dumps(summarize(bytes(raw)),indent=2))
  if not row['passed'] and name == 'before':raise RuntimeError('No ready console; no Add launched')
# Background observation is bounded; a stuck task is not forcibly killed.
raise SystemExit(0 if all(x['passed'] for x in rows) else 1)
