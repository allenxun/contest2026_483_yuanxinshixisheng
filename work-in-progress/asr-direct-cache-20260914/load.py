"""Use the reviewed RAM-only OTG helpers for the direct-cache package."""

import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
HELPERS = PROJECT / "work-in-progress/tts-spoken-flow-20260913"
environment = os.environ.copy()
environment["K7VOICE_PACKAGE_DIR"] = str(HERE)
environment["K7VOICE_MANIFEST"] = str(HERE / "clean-tls-prefix-package.json")
environment["K7VOICE_PAYLOAD"] = str(HERE / "prompt-asr-direct-clean-tls-prefix.bin")

if len(sys.argv) != 2 or sys.argv[1] not in ("enter", "transfer"):
    raise SystemExit("usage: load.py enter|transfer")
command = ([sys.executable, str(HELPERS / "load_prefix.py"), "enter"]
           if sys.argv[1] == "enter" else
           [sys.executable, str(HELPERS / "transfer_and_boot.py")])
raise SystemExit(subprocess.run(command, env=environment, check=False).returncode)
