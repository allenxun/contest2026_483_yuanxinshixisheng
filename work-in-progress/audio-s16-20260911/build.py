import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
sdk = Path('/home/swl/openvela')
build = sdk / 'cmake_out/velavision_audio_s16_20260911'
assert not build.exists()

runtime = sdk / 'work/native-emutls-fix/runtime.o'
runtime_hash = hashlib.sha256(runtime.read_bytes()).hexdigest()
assert runtime_hash == '953dd51e573cb78daaf7f21f457e7f695585f66c7c5803ec2a109efa03256f17'

command = (
    f'source build/envsetup.sh && '
    f'cmake -S nuttx -B {build} -G Ninja '
    '-DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local '
    '-DK7VOICE_NATIVE_ORT_ADD=ON '
    '-DK7VOICE_NATIVE_ASR_MODEL=ON '
    '-DK7VOICE_NATIVE_ASR_MIC=ON '
    f'-DK7VOICE_ORT_OBJECT={runtime} '
    f'-DK7VOICE_ORT_OBJECT_SHA256={runtime_hash} && '
    f'cmake --build {build} -j4'
)

with (root / 'build.log').open('xb') as log:
    process = subprocess.run(
        ['bash', '-c', command], cwd=sdk, stdout=log,
        stderr=subprocess.STDOUT, timeout=1800)

result = {'exit_code': process.returncode, 'command': command}
if process.returncode == 0:
    result['sha256'] = hashlib.sha256((build / 'nuttx.bin').read_bytes()).hexdigest()
(root / 'build-result.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
