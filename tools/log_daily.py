"""User-selected daily layout; callers hold the shared log writer lock."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

DAILY_SESSIONS = {
    '01a07ed4-3f0d-7450-8bb1-bb756849cb4e',
    '01a06679-4033-7993-b989-6269e03e0e70',
}
LOCAL_TIME = timezone(timedelta(hours=8))

def partition(events, sid, started_at):
    days = {}
    for event in events:
        day = (datetime.fromisoformat(event['ts'].replace('Z', '+00:00')).astimezone(LOCAL_TIME).date().isoformat()
               if sid in DAILY_SESSIONS else started_at[:10])
        days.setdefault(day, []).append(event)
    return days

def write_session(root, login, sid, events, started_at):
    parts = []
    for day, entries in sorted(partition(events, sid, started_at).items()):
        rel = f'logs/{login}/{day}/codex__{sid}.jsonl'
        path = root/rel
        data = ''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in entries).encode('utf-8')
        part = dict(file_path=rel, event_count=len(entries), sha256=hashlib.sha256(data).hexdigest())
        if path.is_file() and path.read_bytes() == data:
            parts.append(part)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.daily-')
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        parts.append(part)
    return parts
