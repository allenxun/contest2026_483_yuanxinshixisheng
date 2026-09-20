"""Enable the panel only after this firmware's recorded RAM and audio checks."""
import json
from pathlib import Path
import re

project = Path(__file__).resolve().parents[2]
work = project / 'work-in-progress/voice-ui-connect-20260913'
boot = json.loads(sorted(work.glob('fixed-fixture-boot-*.json'))[-1].read_text())
assert boot['ram_boot_reached_nsh'] and boot['usb_ack']
assert boot['payload_sha256'] == 'c95b9aa6b599fdf5c942af0398ba82936f8324f5702c417d247811ed7299e4e0'
prepare = sorted(work.glob('voice-prepare-*.log'))[-1].read_bytes()
assert b'WIFI shared start ret=0' in prepare and b'VOICE native_network=1' in prepare
ready = project / 'evidence/voice-panel-20260913/connect-board-ready'
ready.write_text('voice-ui-connect-20260913; RAM verified; radio initialized\n')
print('Manual Wi-Fi panel enabled; actual user connection remains to be tested')
