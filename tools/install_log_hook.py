"""Merge the project-scoped Stop hook without changing trust or other hooks."""
import json
import base64
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
home = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
target = home/'hooks.json'
config = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {}
script = "$OutputEncoding = [System.Text.UTF8Encoding]::new(); [Console]::In.ReadToEnd() | & '" + sys.executable.replace("'", "''") + "' -X utf8 '" + str(root/'tools/auto_collect_logs.py').replace("'", "''") + "'; exit $LASTEXITCODE"
# PowerShell's standard UTF-16 transport avoids two nested shells interpreting paths.
command = 'powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + base64.b64encode(script.encode('utf-16-le')).decode('ascii')
groups = config.setdefault('hooks', {}).setdefault('Stop', [])
for group in groups:
    group['hooks'] = [h for h in group.get('hooks', []) if str(root/'tools/auto_collect_logs.py') not in h.get('commandWindows', '')]
if not any(h.get('commandWindows') == command for group in groups for h in group.get('hooks', [])):
    groups.append({'hooks': [{'type': 'command', 'command': command, 'commandWindows': command, 'timeout': 120}]})
    if target.exists():
        shutil.copy2(target, target.with_name('hooks.json.backup-' + datetime.now().strftime('%Y%m%d-%H%M%S')))
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(str(target))
print('Installed Stop hook configuration. Review/trust in Codex /hooks; restart task and perform real conversation acceptance.')
