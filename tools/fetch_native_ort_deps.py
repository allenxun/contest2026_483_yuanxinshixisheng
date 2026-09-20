"""Fetch only reviewed common-platform prerequisites using upstream digest pins."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'work-in-progress/native-voice-sources'
DEPS = BASE / 'onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d/cmake/deps.txt'
OUT = BASE / 'deps'
OUT.mkdir(exist_ok=True)
selected = {'abseil_cpp', 'date', 'eigen', 'microsoft_gsl', 'safeint'}
if sys.argv[1:]:
    assert sys.argv[1:] == ['--nsync-only']
    selected = {'google_nsync'}
failures = []
for line in DEPS.read_text().splitlines():
    if not line or line.startswith('#'):
        continue
    name, url, expected = line.split(';')
    if name not in selected:
        continue
    selected.remove(name)
    target = OUT / (name + '.zip')
    if target.exists():
        data = target.read_bytes()
    else:
        # GitHub archive and codeload serve the same pinned zip, checked below.
        fetch_url = url
        if url.startswith('https://github.com/') and '/archive/' in url:
            repo, revision = url[len('https://github.com/'):].split('/archive/', 1)
            fetch_url = 'https://codeload.github.com/' + repo + '/zip/' + revision.removesuffix('.zip')
        with urllib.request.urlopen(fetch_url, timeout=60) as response:
            data = response.read(50 * 1024 * 1024 + 1)
        assert len(data) <= 50 * 1024 * 1024
    if hashlib.sha1(data).hexdigest() != expected:
        failures.append(dict(name=name, reason='upstream digest mismatch',
            bytes=len(data), actual_sha256=hashlib.sha256(data).hexdigest(), expected_sha1=expected))
        print(name, 'rejected: upstream digest mismatch', flush=True)
        continue
    if not target.exists():
        with target.open('xb') as stream:
            stream.write(data)
    target.with_suffix('.json').write_text(json.dumps(dict(name=name, upstream_url=url,
        upstream_sha1=expected, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
        deps_file_sha256=hashlib.sha256(DEPS.read_bytes()).hexdigest(), compiled=False), indent=2))
    print(name, len(data), 'upstream digest verified', flush=True)
assert not selected, selected
(OUT / ('nsync-fetch-failures.json' if sys.argv[1:] else 'fetch-failures.json')).write_text(json.dumps(failures, indent=2))
if failures:
    raise SystemExit(1)
