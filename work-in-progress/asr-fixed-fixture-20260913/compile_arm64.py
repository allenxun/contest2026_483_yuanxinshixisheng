"""Compile the frozen diagnostic candidate without modifying SDK sources."""
import hashlib
import json
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
sdk = Path('/home/swl/openvela')
prior = sdk / 'work/native-asr-recognizer'
generated = sdk / 'cmake_out/velavision_voice_tls_20260911'
header = sdk / 'work/native-vits-lexicon-20260911/sherpa'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = here / 'runtime-after.cpp'
assert sha(source) == '4a976bb90e562ac034d81fc7c0a27c01d618086b491808082272b4fc894df93b'
assert sha(header / 'sherpa-onnx/c-api/c-api.h') == 'e286ded904e93b670ad229d88151dfade58671fc2740a0afb11b0372f3595100'
command = json.loads((prior / 'compile-attempt2.json').read_text())['command']
command = [x.replace('/dev/shm/velavision_audio_sound_20260910', str(generated)) for x in command]
# Keep the real immutable model fixture; the host mock header is deliberately
# not on this compile's quoted-include search path.
source_dir = here / 'arm64-input'
source_dir.mkdir(exist_ok=True)
target = source_dir / 'native_asr_runtime.cpp'
target.write_bytes(source.read_bytes())
obj = here / 'runtime-arm64.o'
command[command.index('-c') + 1] = str(target)
command[command.index('-o') + 1] = str(obj)
command += ['-I' + str(header), '-I' + str(prior)]
with (here / 'arm64.log').open('wb') as log:
    result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
record = {'command': command, 'exit_code': result.returncode,
          'source_sha256': sha(target), 'fixture_sha256': sha(prior / 'test_assets.h'),
          'object_sha256': sha(obj) if result.returncode == 0 else None,
          'scope': 'ARM64 object only; not linked or deployed'}
(here / 'arm64-result.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
raise SystemExit(result.returncode)
