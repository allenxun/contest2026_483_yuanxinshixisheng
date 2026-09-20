"""Run the reviewed gated speech image through the RAM-only OTG helpers."""

import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROJECT = Path('/home/swl/openvela/work/velavision-project')
HELPERS = PROJECT / 'work-in-progress/tts-spoken-flow-20260913'
environment = os.environ.copy()
environment['K7VOICE_PACKAGE_DIR'] = str(HERE)
environment['K7VOICE_MANIFEST'] = str(HERE / 'flowui-prefix-package.json')
environment['K7VOICE_PAYLOAD'] = str(HERE / 'spoken-tts-gated-flowui-prefix.bin')

if len(sys.argv) != 2 or sys.argv[1] not in ('enter', 'transfer'):
    raise SystemExit('usage: load_flowui.py enter|transfer')
if sys.argv[1] == 'enter':
    command = [sys.executable, str(HELPERS / 'load_prefix.py'), 'enter']
else:
    command = [sys.executable, str(HELPERS / 'transfer_and_boot.py')]
raise SystemExit(subprocess.run(command, env=environment, check=False).returncode)





