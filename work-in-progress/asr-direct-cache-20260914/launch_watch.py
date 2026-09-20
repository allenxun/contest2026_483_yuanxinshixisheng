"""Launch one detached RAM-only loader watcher without overwriting evidence."""

import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
LOG = HERE / "watch-direct-clean-tls-20260914.log"
with LOG.open("xb") as output:
    process = subprocess.Popen(
        [sys.executable, str(HERE / "watch_load.py")],
        cwd=str(HERE), stdin=subprocess.DEVNULL,
        stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
print(process.pid)
