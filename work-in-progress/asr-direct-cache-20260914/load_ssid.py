"""Load the reviewed dynamic-SSID prompt package through RAM-only helpers."""

import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path("/home/swl/openvela/work/velavision-project")
HELPERS = PROJECT / "work-in-progress/tts-spoken-flow-20260913"
environment = os.environ.copy()
environment["K7VOICE_PACKAGE_DIR"] = str(HERE)
environment["K7VOICE_MANIFEST"] = str(HERE / "ssid-prefix-package.json")
environment["K7VOICE_PAYLOAD"] = str(HERE / "prompt-asr-direct-ssid-prefix.bin")

if len(sys.argv) != 2 or sys.argv[1] != "transfer":
    raise SystemExit("usage: load_ssid.py transfer")
raise SystemExit(subprocess.run(
    [sys.executable, str(HELPERS / "transfer_and_boot.py")],
    env=environment, check=False,
).returncode)
