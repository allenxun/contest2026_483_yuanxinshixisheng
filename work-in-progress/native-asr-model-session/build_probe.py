"""Run in the copied Ubuntu candidate directory; no device access."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
previous = json.loads((root / 'compile-result.json').read_text())
command = previous['command']
result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
(root / 'compile-model.log').write_bytes(result.stdout)
assert result.returncode == 0, result.stdout.decode(errors='replace')
c_command = [arg for arg in command if not arg.startswith('-std=') and arg != '-nostdinc++']
c_command[0] = c_command[0].replace('-g++', '-gcc')
c_command.append('-I' + str(root / 'vendor'))
c_command[c_command.index('-c') + 1] = str(root / 'sha256_vendor.c')
c_command[c_command.index('-o') + 1] = str(root / 'sha256_vendor.o')
result = subprocess.run(c_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
(root / 'compile-sha.log').write_bytes(result.stdout)
assert result.returncode == 0, result.stdout.decode(errors='replace')
runtime = Path('/home/swl/openvela/work/native-vits-lexicon-20260911/link1/session.o')
assert hashlib.sha256(runtime.read_bytes()).hexdigest() == 'e43242de83135f400ee8c72668813d92c534f6b6f0020e3525f14904d6a4c767'
output = root / 'decoder-runtime.o'
assert not output.exists(), 'Keep completed outputs immutable; use a new candidate for another link'
link = [command[0].replace('-g++', '-ld'), '-r', '-o', str(output),
        str(root / 'model_session.o'), str(root / 'sha256_vendor.o'), str(runtime)]
result = subprocess.run(link, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
(root / 'link-model.log').write_bytes(result.stdout)
report = dict(exit_code=result.returncode, compile_command=command, sha_command=c_command,
              link_command=link, firmware_linked=False, board_tested=False)
report['inputs'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [root / 'model_session.cpp', root / 'shared_runtime.hpp',
                              root / 'model_lock.h', root / 'sha256_vendor.c', runtime]}
if result.returncode == 0:
    report['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    report['output_bytes'] = output.stat().st_size
(root / 'link-result.json').write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k not in
                  ('inputs', 'compile_command', 'sha_command', 'link_command')}))
