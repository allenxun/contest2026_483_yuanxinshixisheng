import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
PROJECT = SDK / 'work/velavision-project'
BUILD = SDK / 'cmake_out/velavision_spoken_tts_gated_sharedcache_20260914'
RUNTIME = HERE / 'speech-runtime-gated-sharedcache.arm64.o'
EXPECTED_RUNTIME = '8c2b5f75cb89e5434213c55b432b2b6d3ac855067cc4c6817ea686f643bcf380'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if sha(RUNTIME) != EXPECTED_RUNTIME:
    raise RuntimeError('gated speech runtime hash changed')
if BUILD.exists():
    raise RuntimeError('keep previous build evidence immutable')
prior = json.loads((PROJECT / 'work-in-progress/tts-spoken-flow-20260913/result-speech.json').read_text())
expected_inputs = dict(prior['inputs'])
expected_inputs['app/k7sound/k7sound_main.c'] = \
    '7bed3306139af1ea6c15ec6c6c8da52472e231c2a672bb8aab3ff78c1f0b0456'
expected_inputs['app/voicelink/src/k7voice_main.cpp'] = \
    'e70022cbb53ad0c4720b2e84c1a9deb89c4bca0cfb491d991774ef3d8eaed00e'
for name, digest in expected_inputs.items():
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
    'inputs': expected_inputs,
    'shared_runtime_gate': True,
    'persistent_asr_cache': True,
    'persistent_tts_cache': True,
    'tts_speaker_id': 21,
    'speech_gain_db': 18,
    'board_tested': False,
}
for phase, command in [('configure', configure),
                       ('build', ['cmake', '--build', str(BUILD), '-j4'])]:
    with (HERE / ('sharedcache-' + phase + '.log')).open('xb') as log:
        result = subprocess.run(command, cwd=SDK, env=environment,
                                stdout=log, stderr=subprocess.STDOUT,
                                timeout=2400)
    record[phase + '_exit_code'] = result.returncode
    (HERE / 'sharedcache-firmware-result.json').write_text(
        json.dumps(record, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(phase + ' failed; inspect retained log')
record['artifacts'] = {
    name: {'bytes': (BUILD / name).stat().st_size,
           'sha256': sha(BUILD / name)}
    for name in ('nuttx', 'nuttx.bin', '.config')
}
(HERE / 'sharedcache-firmware-result.json').write_text(
    json.dumps(record, indent=2) + '\n')
print(json.dumps(record['artifacts'], indent=2))








