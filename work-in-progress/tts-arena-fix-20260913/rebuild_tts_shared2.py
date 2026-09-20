import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK = Path('/home/swl/openvela')
TTS_BUILD = SDK / 'work/native-vits-lexicon-20260911/build'
TTS_SOURCE = SDK / 'work/native-vits-lexicon-20260911/sherpa'
CURRENT = HERE / 'speech-runtime-shared2-asr.arm64.o'
TOOL = SDK / 'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin'
FINAL_BUILD = SDK / 'cmake_out/velavision_spoken_tts_20260913'


def run(command, log_name):
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=300)
    (HERE / log_name).write_bytes(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{log_name} failed with {result.returncode}')
    return result.stdout


entries = json.loads((TTS_BUILD / 'compile_commands.json').read_text())
entry = next(x for x in entries if x['file'].endswith('offline-tts-vits-model.cc'))
command = shlex.split(entry['command'])
source = HERE / 'offline-tts-vits-model.cc'
replacement = HERE / 'offline-tts-vits-model-shared2.cc.o'
command[command.index('-c') + 1] = str(source)
command[command.index('-o') + 1] = str(replacement)

rewritten = []
for arg in command:
    if arg == '-I/dev/shm/velavision-ort-session-20260911/ort/include/onnxruntime/core/session':
        rewritten.append('-I' + str(HERE))
    elif arg == '-I/dev/shm/velavision-sherpa-asr-20260911/sherpa':
        rewritten.append('-I' + str(TTS_SOURCE))
    elif arg == '-I/dev/shm/velavision_audio_sound_20260910/apps/include':
        rewritten.append('-I' + str(FINAL_BUILD / 'apps/include'))
    elif arg == '-I/dev/shm/velavision_audio_sound_20260910/include/libcxx':
        rewritten.append('-I' + str(FINAL_BUILD / 'include/libcxx'))
    elif arg == '-I/dev/shm/velavision_audio_sound_20260910/include/libcxx_config':
        rewritten.append('-I' + str(FINAL_BUILD / 'include/libcxx_config'))
    elif arg == '-I/dev/shm/velavision_audio_sound_20260910/include/libcxxabi':
        rewritten.append('-I' + str(FINAL_BUILD / 'include/libcxxabi'))
    elif arg == '/dev/shm/velavision_audio_sound_20260910/include':
        rewritten.append(str(FINAL_BUILD / 'include'))
    else:
        rewritten.append(arg)
command = rewritten
command[command.index('-c'):command.index('-c')] = [
    '-I' + str(HERE),
    '-I' + str(SDK / 'work/native-asr-recognizer'),
    '-DK7_TTS_NATIVE_STORAGE=1',
]
run(command, 'shared2-compile-tts-model.log')

ar = str(TOOL / 'aarch64-none-elf-ar')
nm = str(TOOL / 'aarch64-none-elf-nm')
objcopy = str(TOOL / 'aarch64-none-elf-objcopy')
ld = str(TOOL / 'aarch64-none-elf-ld')
archive = SDK / 'work/native-asr-recognizer/link2/libsherpa-onnx-core.a'
member = 'offline-tts-vits-model.cc.obj'
original = HERE / 'offline-tts-vits-model-shared2.original.o'
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
    raise RuntimeError('no strong symbols found in original TTS model member')

weakened = HERE / 'speech-runtime-shared2-asr-tts-weakened.o'
shutil.copyfile(CURRENT, weakened)
run([objcopy, *['--weaken-symbol=' + s for s in symbols], str(weakened)],
    'shared2-weaken-tts-model.log')
fixed = HERE / 'speech-runtime-shared2-base.arm64.o'
run([ld, '-r', '--strip-debug', '-o', str(fixed), str(replacement),
     str(weakened)], 'shared2-link-tts-model.log')

nm_text = subprocess.check_output([nm, '-g', str(fixed)], text=True)
result = {
    'status': 'pass',
    'current_sha256': hashlib.sha256(CURRENT.read_bytes()).hexdigest(),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'replacement_sha256': hashlib.sha256(replacement.read_bytes()).hexdigest(),
    'fixed_bytes': fixed.stat().st_size,
    'fixed_sha256': hashlib.sha256(fixed.read_bytes()).hexdigest(),
    'weakened_symbols': symbols,
    'compile_command': command,
    'tts_entry_count': nm_text.count(' T k7_tts_synthesize'),
    'firmware_linked': False,
    'board_tested': False,
}
if result['tts_entry_count'] != 1:
    result['status'] = 'fail'
(HERE / 'shared2-base-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items()
                  if k not in ('compile_command', 'weakened_symbols')}, indent=2))
if result['status'] != 'pass':
    raise SystemExit(1)






