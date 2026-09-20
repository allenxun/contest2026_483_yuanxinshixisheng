"""Replace idle panel processes; refuse to interrupt a serial transaction."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        if proc.stat().st_uid != os.getuid(): continue
        if str(here / 'wake_panel.py').encode() not in (proc / 'cmdline').read_bytes(): continue
        for fd in (proc / 'fd').iterdir():
            assert '/dev/ttyUSB' not in os.readlink(fd), 'Panel is using serial; stop in UI before replacing'
        os.kill(int(proc.name), signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError):
        pass
time.sleep(.5)
subprocess.run([sys.executable, str(here / 'launch_panel.py')], check=True)
