"""Continue this active RAM-load pipeline with a bounded actual Add test."""
import subprocess,sys,time,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/voice-ort-add-20260911'
start=time.monotonic();p=E/'ramload-progress.txt'
while time.monotonic()-start<2700:
 text=p.read_text(encoding='utf-8-sig',errors='replace')
 if 'Traceback (most recent call last)' in text:raise RuntimeError('RAM loader failed; no probe started')
 if 'PASS: REAL K7 NSH' in text:
  time.sleep(1)  # Loader prints inside its serial context; allow context to close.
  break
 time.sleep(2)
else:raise RuntimeError('RAM load wait expired; no board operation')
out=E/'automatic-add-test.log'
with out.open('xb') as f:
 q=subprocess.run([sys.executable,'-u','-X','utf8',str(R/'tools/test_voice_ort_add_board.py')],stdout=f,stderr=subprocess.STDOUT,timeout=100)
(E/'automatic-add-test-result.json').write_text(json.dumps(dict(exit_code=q.returncode,wait_seconds=time.monotonic()-start,asr_tested=False,tts_tested=False),indent=2))
print(out.read_text(errors='replace'),flush=True)
raise SystemExit(q.returncode)
