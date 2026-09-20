"""Launch the full spoken-provision panel on the logged-in Ubuntu desktop."""
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
env = dict(os.environ)
allowed = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
           'DBUS_SESSION_BUS_ADDRESS'}
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if proc.stat().st_uid != os.getuid():
            continue
        if b'gnome-session-binary' not in (proc / 'cmdline').read_bytes():
            continue
        for item in (proc / 'environ').read_bytes().split(b'\0'):
            key, sep, value = item.partition(b'=')
            if sep and key.decode(errors='replace') in allowed:
                env[key.decode()] = value.decode()
    except (OSError, PermissionError):
        continue
evidence = here.parents[1] / 'evidence/chat-panel-20260915'
evidence.mkdir(parents=True, exist_ok=True)
with (evidence / 'panel-console.log').open('ab') as log:
    child = subprocess.Popen([
        sys.executable, str(here / 'chat_panel.py'),
        '--snapshot', str(evidence / 'panel.png')],
        env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
print('panel_pid=' + str(child.pid))
