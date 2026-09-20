"""Fetch pinned upstream source archives to Windows storage; no SDK or board use."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work-in-progress/native-voice-sources'
OUT.mkdir(exist_ok=True)
SOURCES = [
    ('onnxruntime', 'microsoft/onnxruntime', '8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'),
    ('sherpa-onnx', 'k2-fsa/sherpa-onnx', '26aa2fa93210376a89de3a65a1a4dd320c37f5e9'),
]
for name, repo, commit in SOURCES:
    target = OUT / (name + '-' + commit + '.tar.gz')
    report = target.with_suffix('.json')
    if target.exists():
        old = json.loads(report.read_text())
        assert hashlib.sha256(target.read_bytes()).hexdigest() == old['sha256']
        print(name, 'existing archive verified', flush=True)
        continue
    url = 'https://codeload.github.com/' + repo + '/tar.gz/' + commit
    partial = target.with_suffix('.partial-' + time.strftime('%Y%m%d-%H%M%S'))
    digest = hashlib.sha256()
    size = 0
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=60) as response, partial.open('xb') as stream:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > 300 * 1024 * 1024 or time.monotonic() - started > 600:
                raise RuntimeError('Source download exceeded size/time bound')
            stream.write(block)
            digest.update(block)
    partial.rename(target)
    report.write_text(json.dumps(dict(url=url, commit=commit, bytes=size,
        sha256=digest.hexdigest(), compiled=False, dependencies_complete=False), indent=2))
    print(name, size, digest.hexdigest(), flush=True)
