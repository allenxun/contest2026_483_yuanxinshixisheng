"""Install hash-locked host conversion tools in an isolated project directory."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads((root/'evidence/native-ort-host-converter-resolution-20260911.json').read_text())
lock = root/'work-in-progress/native-ort-host-converter-requirements.txt'
target = root/'work-in-progress/native-ort-host-converter-python'
assert not target.exists(), 'Use a fresh directory; do not mix environments'
lines = []
versions = {}
for item in report['install']:
    name = item['metadata']['name']
    version = item['metadata']['version']
    digest = item['download_info']['archive_info']['hashes']['sha256']
    versions[name.lower()] = version
    assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
    lines.append(f'{name}=={version} --hash=sha256:{digest}')
assert versions['onnxruntime'] == '1.17.1'
assert versions['numpy'] == '1.26.4'
lock.write_text('\n'.join(sorted(lines))+'\n', encoding='utf-8')
subprocess.run([sys.executable,'-m','pip','install','--require-hashes','--only-binary=:all:',
                '--no-cache-dir','--ignore-installed','--target',str(target),
                '--report',str(root/'evidence/native-ort-host-converter-install-20260911.json'),
                '-r',str(lock)], check=True)
sys.path.insert(0, str(target))
import onnxruntime
import numpy
import onnx
assert onnxruntime.__version__ == '1.17.1'
assert numpy.__version__ == '1.26.4'
print(json.dumps(dict(ort=onnxruntime.__version__,numpy=numpy.__version__,onnx=onnx.__version__,
                     host_only=True,board_inference=False)))
