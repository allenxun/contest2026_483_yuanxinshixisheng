"""Record the bounded two-invocation board test from immutable raw logs."""
import hashlib,json,re
from pathlib import Path
r=Path(__file__).resolve().parent
names=['probe-20260911-185540.log','probe-20260911-185642.log']
rows=[]
for name in names:
    data=(r/name).read_bytes()
    text=data.decode('utf-8',errors='replace')
    assert 'TLS_CHECK PASS workers=2 destructors=2 main_value=123' in text
    assert 'ASR_STORAGE peak=468101988 live=0 records=1264 failures=0 reason=0' in text
    result=re.search(r'ASR_INFER RESULT seconds=([\d.]+) text=([^\r\n]+)',text)
    assert result and 'PANIC' not in text and 'Assertion failed' not in text
    rows.append(dict(log=name,sha256=hashlib.sha256(data).hexdigest(),seconds=float(result[1]),text=result[2]))
assert rows[0]['text']==rows[1]['text']
report=dict(revision='voice-tls-20260911',firmware_sha256='86631d2091e9b5c2a155e2a83d28eeeebca860706d557264c667d4bf73a365df',
            consecutive_separate_tasks=2,runs=rows,passed=True,
            scope='Fixed WAV, full real ASR, task TLS isolation and worker destructors; not microphone accuracy, long stability or voice Wi-Fi acceptance')
(r/'board-repeat-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
