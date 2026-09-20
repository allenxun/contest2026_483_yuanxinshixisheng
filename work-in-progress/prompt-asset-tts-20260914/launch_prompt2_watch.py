"""Launch the prompt2 watcher detached, retaining all output in the project."""

import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
LOG = HERE / ("watch-prompt2-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
with LOG.open("xb") as output:
    process = subprocess.Popen(
        [sys.executable, str(HERE / "watch_prompt2.py")],
        cwd=str(HERE), stdout=output, stderr=subprocess.STDOUT,
        start_new_session=True, close_fds=True,
    )
print("pid=%d" % process.pid)
print("log=" + str(LOG))
