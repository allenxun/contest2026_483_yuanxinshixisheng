import os,signal
from pathlib import Path
target=b'/home/swl/openvela/work/velavision-project/host/voice/wake_panel.py'
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        if proc.stat().st_uid!=os.getuid() or target not in (proc/'cmdline').read_bytes():continue
        for fd in (proc/'fd').iterdir():
            assert '/dev/ttyUSB' not in os.readlink(fd),'Active panel transaction; do not interrupt'
        os.kill(int(proc.name),signal.SIGTERM)
    except (FileNotFoundError,ProcessLookupError):pass
print('Idle panel released for firmware test')
