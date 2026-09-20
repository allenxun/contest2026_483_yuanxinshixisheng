"""Audited two-file SDK advance and independent firmware build. No board I/O."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
sdk = Path('/home/swl/openvela')
build = sdk / 'cmake_out/velavision_voice_asr_model_20260911'
assert not build.exists(), 'Do not overwrite an independent build'
pairs = []
for name, suffix in [('CMakeLists.txt', 'CMakeLists.txt'),
                     ('k7voice_main.cpp', 'src/k7voice_main.cpp')]:
    for base in [sdk / 'apps/examples/voicelink',
                 sdk / 'work/velavision-project/app/voicelink']:
        target = base / suffix
        assert target.read_bytes() == (root / ('baseline-' + name)).read_bytes(), str(target)
        pairs.append((root / name, target))
report = []
for source, target in pairs:
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_bytes(source.read_bytes())
    report.append(dict(path=str(target), before=before,
                       after=hashlib.sha256(target.read_bytes()).hexdigest()))
(root / 'sdk-entry-change.json').write_text(json.dumps(report, indent=2))
runtime = root / 'decoder-runtime.o'
digest = hashlib.sha256(runtime.read_bytes()).hexdigest()
assert digest == json.loads((root / 'link-result.json').read_text())['output_sha256']
command = ('source build/envsetup.sh && cmake -S nuttx -B ' + str(build) +
           ' -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local'
           ' -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON'
           ' -DK7VOICE_ORT_OBJECT=' + str(runtime) +
           ' -DK7VOICE_ORT_OBJECT_SHA256=' + digest +
           ' && cmake --build ' + str(build) + ' -j4')
with (root / 'firmware-build.log').open('wb') as log:
    result = subprocess.run(['bash', '-c', command], cwd=sdk, stdout=log,
                            stderr=subprocess.STDOUT, timeout=1800)
summary = dict(exit_code=result.returncode, command=command, board_tested=False)
if result.returncode == 0:
    summary['binary_sha256'] = hashlib.sha256((build / 'nuttx.bin').read_bytes()).hexdigest()
(root / 'firmware-result.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
