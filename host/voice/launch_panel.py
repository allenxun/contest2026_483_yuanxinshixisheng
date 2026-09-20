"""Launch on the logged-in Ubuntu desktop without taking serial ownership."""
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
env = dict(os.environ)
allowed = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS'}
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if proc.stat().st_uid != os.getuid():
            continue
        command = (proc / 'cmdline').read_bytes()
        if b'gnome-session-binary' not in command:
            continue
        for item in (proc / 'environ').read_bytes().split(b'\0'):
            key, sep, value = item.partition(b'=')
            if sep and key.decode(errors='replace') in allowed:
                env[key.decode()] = value.decode()
    except (OSError, PermissionError):
        continue
evidence = here.parents[1] / 'evidence/voice-panel-20260913'
evidence.mkdir(parents=True, exist_ok=True)
with (evidence / 'panel-console.log').open('ab') as log:
    child = subprocess.Popen([sys.executable, str(here / 'wake_panel.py'), '--cued',
                              '--ready-file', str(evidence / 'connect-board-ready'),
                              '--snapshot', str(evidence / 'panel.png')],
                             env=env, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
print('panel_pid=' + str(child.pid))
