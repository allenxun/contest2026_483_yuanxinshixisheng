import hashlib
import json
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
ASR = SDK / 'work/native-asr-recognizer'
TTS_SOURCE = SDK / 'work/native-vits-lexicon-20260911/sherpa'
FIRMWARE_BUILD = SDK / 'cmake_out/velavision_spoken_tts_20260913'
BASE = HERE / 'speech-runtime-fixed.arm64.o'
TOOL = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'


def run(command, log_name):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=300)
    (HERE / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{log_name} failed with {result.returncode}')


record = json.loads((SDK / 'work/velavision-project/work-in-progress/voice-ui-connect-20260913/result.json').read_text(encoding='utf-8-sig'))
template = list(record['compile'][0]['command'])
rewrites = {
    '-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session': '-I' + str(HERE),
    '-I/dev/shm/velavision-sherpa-asr-20260911/sherpa': '-I' + str(TTS_SOURCE),
    '-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/apps/include': '-I' + str(FIRMWARE_BUILD / 'apps/include'),
    '-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxx': '-I' + str(FIRMWARE_BUILD / 'include/libcxx'),
    '-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxx_config': '-I' + str(FIRMWARE_BUILD / 'include/libcxx_config'),
    '-I/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include/libcxxabi': '-I' + str(FIRMWARE_BUILD / 'include/libcxxabi'),
    '/home/swl/openvela/cmake_out/velavision_voice_tls_20260911/include': str(FIRMWARE_BUILD / 'include'),
}
template = [rewrites.get(argument, argument) for argument in template]
template[template.index('-c'):template.index('-c')] = ['-I' + str(HERE)]

objects = []
commands = []
for name, tts in [('native_asr_runtime.cpp', False),
                  ('native_tts_runtime.cpp', True),
                  ('speech_runtime_gate.cpp', False)]:
    command = list(template)
    command[command.index('-c') + 1] = str(HERE / name)
    output = HERE / (name + '.o')
    command[command.index('-o') + 1] = str(output)
    if tts:
        command = ['-DSHERPA_ONNX_ENABLE_TTS=1'
                   if item == '-DSHERPA_ONNX_ENABLE_TTS=0' else item
                   for item in command]
    run(command, 'compile-' + name + '.log')
    objects.append(output)
    commands.append(command)

nm = str(TOOL / 'aarch64-none-elf-nm')
objcopy = str(TOOL / 'aarch64-none-elf-objcopy')
ld = str(TOOL / 'aarch64-none-elf-ld')
symbols = []
for item in objects:
    lines = subprocess.check_output(
        [nm, '-g', '--defined-only', str(item)], text=True).splitlines()
    for line in lines:
        fields = line.split()
        if len(fields) >= 3 and fields[-2].upper() not in ('U', 'W', 'V'):
            symbols.append(fields[-1])
symbols = sorted(set(symbols))
required = {
    'k7_asr_audio_text', 'k7_asr_model_session_probe',
    'k7_asr_microphone_text', 'k7_asr_microphone_probe',
    'k7_tts_synthesize', 'k7_speech_runtime_try_acquire',
    'k7_speech_runtime_release',
}
if not required.issubset(symbols):
    raise RuntimeError('missing replacement wrapper symbols')

base_undefined = sorted(set(line.split()[-1] for line in
    subprocess.check_output([nm, '-u', str(BASE)], text=True).splitlines()
    if line.split()))
weakened = HERE / 'speech-runtime-wrappers-weakened.o'
shutil.copyfile(BASE, weakened)
run([objcopy, *['--weaken-symbol=' + item for item in symbols], str(weakened)],
    'weaken-wrappers.log')
fixed = HERE / 'speech-runtime-gated.arm64.o'
run([ld, '-r', '--strip-debug', '-o', str(fixed), str(weakened),
     *map(str, objects)], 'link-gated.log')

nm_text = subprocess.check_output([nm, '-g', str(fixed)], text=True)
definitions = [line.split()[-1] for line in nm_text.splitlines()
               if len(line.split()) >= 3 and line.split()[-2] == 'T']
undefined = sorted(set(line.split()[-1] for line in
    subprocess.check_output([nm, '-u', str(fixed)], text=True).splitlines()
    if line.split()))
result = {
    'status': 'pass',
    'base_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
    'output_bytes': fixed.stat().st_size,
    'output_sha256': hashlib.sha256(fixed.read_bytes()).hexdigest(),
    'source_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                      for name, _ in [('native_asr_runtime.cpp', False),
                                      ('native_tts_runtime.cpp', True),
                                      ('speech_runtime_gate.cpp', False)]},
    'commands': commands,
    'weakened_symbols': symbols,
    'added_undefined': sorted(set(undefined) - set(base_undefined)),
    'required_strong_counts': {item: definitions.count(item)
                               for item in sorted(required)},
    'firmware_linked': False,
    'board_tested': False,
}
if result['added_undefined'] or any(value != 1 for value in
                                    result['required_strong_counts'].values()):
    result['status'] = 'fail'
(HERE / 'gated-runtime-result.json').write_text(
    json.dumps(result, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items()
                  if key not in ('commands', 'weakened_symbols')}, indent=2))
if result['status'] != 'pass':
    raise SystemExit(1)
