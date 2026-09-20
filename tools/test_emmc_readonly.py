"""Build/run the host fault-injection test; does not access the board."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[1]
source = root / 'app/k7emmc'
out = root / 'evidence/emmc-source-review-20260910'
compiler = Path('D:/software/mingw64/mingw64/bin/gcc.exe')
exe = out / 'test_sdhci_read.exe'
command = [str(compiler), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
           str(source/'sdhci_read.c'), str(source/'test_sdhci_read.c'), '-o', str(exe)]
subprocess.run(command, check=True)
run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
files = [source/x for x in ('sdhci_read.h','sdhci_read.c','test_sdhci_read.c')]
result = dict(command=command, stdout=run.stdout, returncode=run.returncode,
              hardware_tested=False, firmware_built=False,
              sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'host-test.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(run.stdout, end='')
exe = out / 'test_emmc_init.exe'
command = [str(compiler), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
           str(source/'emmc_init.c'), str(source/'test_emmc_init.c'), '-o', str(exe)]
subprocess.run(command, check=True)
run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
files = sorted(source.glob('*.h')) + sorted(source.glob('*.c'))
result = dict(command=command, stdout=run.stdout, returncode=run.returncode,
              hardware_tested=False, firmware_built=False,
              sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'host-init-test.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(run.stdout, end='')
exe = out / 'test_sdhci_command.exe'
command = [str(compiler), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
           str(source/'sdhci_read.c'), str(source/'sdhci_command.c'),
           str(source/'test_sdhci_command.c'), '-o', str(exe)]
subprocess.run(command, check=True)
run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
files += [source/x for x in ('sdhci_command.h','sdhci_command.c','test_sdhci_command.c')]
result = dict(command=command, stdout=run.stdout, returncode=run.returncode,
              hardware_tested=False, firmware_built=False,
              sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'host-command-test.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(run.stdout, end='')
exe = out / 'test_sdhci_control.exe'
command = [str(compiler), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
           str(source/'sdhci_control.c'), str(source/'sdhci_read.c'),
           str(source/'test_sdhci_control.c'), '-o', str(exe)]
subprocess.run(command, check=True)
run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
files = sorted(source.glob('*.h')) + sorted(source.glob('*.c'))
result = dict(command=command, stdout=run.stdout, returncode=run.returncode,
              hardware_tested=False, firmware_built=False,
              sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'host-control-test.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(run.stdout, end='')
