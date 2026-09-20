from pathlib import Path
import os,subprocess,sys,json
p=Path(__file__).parent
os.environ['PYTHONDONTWRITEBYTECODE']='1'
r=subprocess.run([sys.executable,'-B','test_report.py'],cwd=p,capture_output=True,text=True,timeout=15)
(p/'test-output.txt').write_text(r.stdout+r.stderr)
print(r.stdout+r.stderr)
assert r.returncode==0
sys.path.insert(0,str(p))
from test_report import sample
from report import analyze
before=sample(ACL_QUEUED=0xfffffffe)
after=sample(ACL_QUEUED=1,ACL_SEND_FAIL=1,last_send=-5)
(p/'synthetic-before.txt').write_bytes(before);(p/'synthetic-after.txt').write_bytes(after)
(p/'synthetic-report.json').write_text(json.dumps(analyze(before,after),indent=2))
# CLI rejects truncated input with nonzero exit and emits no successful JSON.
(p/'synthetic-truncated.txt').write_bytes(after[:-3])
r=subprocess.run([sys.executable,'-B','report.py','synthetic-before.txt','synthetic-truncated.txt'],cwd=p,capture_output=True,text=True,timeout=15)
assert r.returncode==2 and not r.stdout
with (p/'test-output.txt').open('a') as f:f.write('CLI truncated input exit=2: '+r.stderr)
