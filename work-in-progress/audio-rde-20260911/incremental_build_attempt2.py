import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
sdk = Path('/home/swl/openvela')
build = sdk / 'cmake_out/velavision_audio_s16_20260911'
assert build.exists()
command = f'source build/envsetup.sh && cmake --build {build} -j4'
with (root / 'build-attempt2.log').open('xb') as output:
    process = subprocess.run(['bash', '-c', command], cwd=sdk, stdout=output,
                             stderr=subprocess.STDOUT, timeout=600)
result = {'exit_code': process.returncode, 'command': command,
          'incremental_from': 'audio-s16-20260911'}
if process.returncode == 0:
    result['sha256'] = hashlib.sha256((build / 'nuttx.bin').read_bytes()).hexdigest()
(root / 'build-attempt2-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
