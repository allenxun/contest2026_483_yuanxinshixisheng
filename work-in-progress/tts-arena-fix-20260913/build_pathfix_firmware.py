import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
PROJECT = SDK / 'work/velavision-project'
BUILD = SDK / 'cmake_out/velavision_spoken_tts_gated_pathfix_20260914'
RUNTIME = HERE / 'speech-runtime-gated-pathfix.arm64.o'
EXPECTED_RUNTIME = 'ea30764813cb5909e1e4c893c74daeeaec42906afb67b82e6612f77f67d9d372'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if sha(RUNTIME) != EXPECTED_RUNTIME:
    raise RuntimeError('gated speech runtime hash changed')
if BUILD.exists():
    raise RuntimeError('keep previous build evidence immutable')
prior = json.loads((PROJECT / 'work-in-progress/tts-spoken-flow-20260913/result-speech.json').read_text())
for name, digest in prior['inputs'].items():
    if sha(PROJECT / name) != digest:
        raise RuntimeError('formal source changed: ' + name)

environment = os.environ.copy()
environment['PATH'] = ':'.join(str(SDK / item) for item in [
    'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin',
    'prebuilts/tools/python/bin',
    'prebuilts/build-tools/linux-x86_64/bin']) + ':' + environment.get('PATH', '')
environment['PYTHONPATH'] = str(SDK / 'prebuilts/tools/python/dist-packages/kconfiglib') + ':' + environment.get('PYTHONPATH', '')
configure = [
    'cmake', '-S', 'nuttx', '-B', str(BUILD), '-G', 'Ninja',
    '-DBOARD_CONFIG=kickpi_k7:velavision_spoken_tts_local',
    '-DK7VOICE_NATIVE_ORT_ADD=ON', '-DK7VOICE_NATIVE_ASR_MODEL=ON',
    '-DK7VOICE_NATIVE_ASR_MIC=ON', '-DK7VOICE_NATIVE_TTS=ON',
    '-DK7VOICE_ORT_OBJECT=' + str(RUNTIME),
    '-DK7VOICE_ORT_OBJECT_SHA256=' + EXPECTED_RUNTIME,
    '-DK7VOICE_TTS_ASSET_INCLUDE=' + str(HERE),
]
record = {
    'runtime_sha256': EXPECTED_RUNTIME,
    'asset_header_sha256': sha(HERE / 'k7tts_assets_generated.h'),
    'inputs': prior['inputs'],
    'shared_runtime_gate': True,
    'board_tested': False,
}
for phase, command in [('configure', configure),
                       ('build', ['cmake', '--build', str(BUILD), '-j4'])]:
    with (HERE / ('pathfix-' + phase + '.log')).open('xb') as log:
        result = subprocess.run(command, cwd=SDK, env=environment,
                                stdout=log, stderr=subprocess.STDOUT,
                                timeout=2400)
    record[phase + '_exit_code'] = result.returncode
    (HERE / 'pathfix-firmware-result.json').write_text(
        json.dumps(record, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(phase + ' failed; inspect retained log')
record['artifacts'] = {
    name: {'bytes': (BUILD / name).stat().st_size,
           'sha256': sha(BUILD / name)}
    for name in ('nuttx', 'nuttx.bin', '.config')
}
(HERE / 'pathfix-firmware-result.json').write_text(
    json.dumps(record, indent=2) + '\n')
print(json.dumps(record['artifacts'], indent=2))

