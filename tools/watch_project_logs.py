"""Local file monitor for the explicitly selected ongoing project session.
No model calls, network, Git operations or hardware access.
"""
import argparse
import json
import os
import time
from pathlib import Path
from auto_collect_logs import ROOT, STATE, collect, save, now

SID = '01a07ed4-3f0d-7450-8bb1-bb756849cb4e'

def main():
    import msvcrt
    parser=argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args=parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'watcher.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0'); lock.flush()
        save(STATE/'watcher.json',dict(pid=os.getpid(),started_at=now(),session_id=SID,interval_seconds=30))
        previous=None
        while True:
            try:
                sources=json.loads((ROOT/'tools/log-sources.json').read_bytes())
                source=next(s for s in sources if s['id']==SID)
                path=Path(source['path'])
                st=path.stat()
                stamp=(st.st_mtime_ns,st.st_size)
                if stamp != previous:
                    result=collect(dict(hook_event_name='Stop',cwd=source['cwd'],session_id=SID,transcript_path=str(path)))
                    if result['status'] != 'collected':
                        raise ValueError('Selected session was skipped')
                    result.update(invocation='local-file-monitor',pid=os.getpid(),source_bytes=st.st_size)
                    save(STATE/'watcher-status.json',result)
                    previous=stamp
                if args.once:
                    return
            except Exception as exc:
                save(STATE/'watcher-error.json',dict(at=now(),error_type=type(exc).__name__))
                if args.once:
                    raise
            time.sleep(30)

if __name__=='__main__': main()
