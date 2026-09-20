import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
ASR = SDK / 'work/native-asr-recognizer'
TTS_SOURCE = SDK / 'work/native-vits-lexicon-20260911/sherpa'
FIRMWARE_BUILD = SDK / 'cmake_out/velavision_spoken_tts_20260913'
BASE = HERE / 'tts-with-current-asr-fixed.arm64.o'
TOOL = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'


def run(command, log_name):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=300)
    (HERE / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{log_name} failed with {result.returncode}')
    return result.stdout


record = json.loads((ASR / 'compile-attempt2.json').read_text())
command = record['command']
source = HERE / 'online-paraformer-model.cc'
replacement = HERE / 'online-paraformer-model.cc.o'
command[command.index('-c') + 1] = str(source)
command[command.index('-o') + 1] = str(replacement)

rewrites = {
    '-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session': '-I' + str(HERE),
    '-I/dev/shm/velavision-sherpa-asr-20260911/sherpa': '-I' + str(TTS_SOURCE),
    '-I/dev/shm/velavision_audio_sound_20260910/apps/include': '-I' + str(FIRMWARE_BUILD / 'apps/include'),
    '-I/dev/shm/velavision_audio_sound_20260910/include/libcxx': '-I' + str(FIRMWARE_BUILD / 'include/libcxx'),
    '-I/dev/shm/velavision_audio_sound_20260910/include/libcxx_config': '-I' + str(FIRMWARE_BUILD / 'include/libcxx_config'),
    '-I/dev/shm/velavision_audio_sound_20260910/include/libcxxabi': '-I' + str(FIRMWARE_BUILD / 'include/libcxxabi'),
    '/dev/shm/velavision_audio_sound_20260910/include': str(FIRMWARE_BUILD / 'include'),
}
command = [rewrites.get(argument, argument) for argument in command]
command[command.index('-c'):command.index('-c')] = ['-I' + str(HERE)]
run(command, 'shared2-compile-asr.log')

ar = str(TOOL / 'aarch64-none-elf-ar')
nm = str(TOOL / 'aarch64-none-elf-nm')
objcopy = str(TOOL / 'aarch64-none-elf-objcopy')
ld = str(TOOL / 'aarch64-none-elf-ld')
archive = ASR / 'link2/libsherpa-onnx-core.a'
member = 'online-paraformer-model.cc.obj'
original = HERE / member
original.write_bytes(subprocess.check_output([ar, 'p', str(archive), member]))
defined = subprocess.check_output([nm, '-g', '--defined-only', str(original)],
                                  text=True).splitlines()
symbols = []
for line in defined:
    fields = line.split()
    if len(fields) >= 3 and fields[-2].upper() not in ('U', 'W', 'V'):
        symbols.append(fields[-1])
symbols = sorted(set(symbols))
if not symbols:
    raise RuntimeError('no strong symbols found in original ASR model member')

weakened = HERE / 'tts-fixed-asr-weakened.o'
shutil.copyfile(BASE, weakened)
run([objcopy, *['--weaken-symbol=' + item for item in symbols], str(weakened)],
    'shared2-weaken-asr.log')
fixed = HERE / 'speech-runtime-shared2-asr.arm64.o'
run([ld, '-r', '--strip-debug', '-o', str(fixed), str(weakened),
     str(replacement)], 'shared2-link-asr.log')

nm_text = subprocess.check_output([nm, '-g', str(fixed)], text=True)
result = {
    'status': 'pass',
    'base_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'storage_sha256': hashlib.sha256((HERE / 'native_model_storage.hpp').read_bytes()).hexdigest(),
    'replacement_sha256': hashlib.sha256(replacement.read_bytes()).hexdigest(),
    'fixed_bytes': fixed.stat().st_size,
    'fixed_sha256': hashlib.sha256(fixed.read_bytes()).hexdigest(),
    'weakened_symbols': symbols,
    'compile_command': command,
    'asr_constructor_count': nm_text.count(' T _ZN11sherpa_onnx21OnlineParaformerModelC1'),
    'tts_entry_count': nm_text.count(' T k7_tts_synthesize'),
    'firmware_linked': False,
    'board_tested': False,
}
if result['asr_constructor_count'] != 1 or result['tts_entry_count'] != 1:
    result['status'] = 'fail'
(HERE / 'shared2-asr-result.json').write_text(
    json.dumps(result, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items()
                  if key not in ('compile_command', 'weakened_symbols')}, indent=2))
if result['status'] != 'pass':
    raise SystemExit(1)


