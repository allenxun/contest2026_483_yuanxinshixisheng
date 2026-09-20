"""Offline asset preparation only; no microphone, board, API or network use."""
import hashlib
import json
import os
import re
import subprocess
import time
import wave
from pathlib import Path

R = Path(__file__).resolve().parents[1]
BASE = R / 'work-in-progress/parallel-voicelink-runtime'
OUT = R / 'work-in-progress/provisioning-fixed-prompts-20260911'
OUT.mkdir(exist_ok=False)
record = json.loads((BASE / 'evidence/tts-cli-20260910T032007632390Z/result.json').read_text())
assert record['exit_code'] == 0
delivery = json.loads((BASE / 'evidence/delivery.json').read_text())
source = R / 'app/voicelink/src/core.cpp'
texts = list(dict.fromkeys(re.findall(r'repeat\("([^"\n]*)"\)', source.read_text())))
texts += ['正在扫描网络', '网络连接成功', '请说要连接的网络名称', '已取消配置']
command = record['command'][:-1]
command[0] = str((BASE / command[0]).resolve())
for item in delivery['inputs_unchanged']:
    path = Path(item['path'])
    if 'vits-icefall-zh-aishell3' in str(path):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
env = dict(os.environ)
env['PATH'] = str(BASE / 'runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib') + os.pathsep + env['PATH']
rows = []
for i, text in enumerate(texts):
    name = 'p%03d' % i
    output = OUT / (name + '.wav')
    cmd = [('--output-filename=' + str(output)) if arg.startswith('--output-filename=') else arg
           for arg in command] + [text]
    started = time.monotonic()
    result = subprocess.run(cmd, cwd=OUT, env=env, capture_output=True, timeout=45)
    (OUT / (name + '.stdout')).write_bytes(result.stdout)
    (OUT / (name + '.stderr')).write_bytes(result.stderr)
    row = dict(id=name, text=text, command=cmd, exit_code=result.returncode,
               seconds=time.monotonic()-started, played_on_board=False)
    rows.append(row)
    (OUT / 'manifest.json').write_text(json.dumps(dict(
        scope='Host-generated fixed audio assets, not board TTS/ASR or provisioning acceptance',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        dynamic_ssid_speech=False, prompts=rows), ensure_ascii=False, indent=2))
    assert result.returncode == 0, result.stderr.decode(errors='replace')[-1500:]
    with wave.open(str(output), 'rb') as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        assert 0 < wav.getnframes() <= wav.getframerate() * 30
        row.update(rate=wav.getframerate(), frames=wav.getnframes(),
                   sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    print(name, text, row['rate'], row['frames'], flush=True)
(OUT / 'manifest.json').write_text(json.dumps(dict(
    scope='Host-generated fixed audio assets; playback and routing still untested',
    dynamic_ssid_speech=False, prompts=rows), ensure_ascii=False, indent=2))
