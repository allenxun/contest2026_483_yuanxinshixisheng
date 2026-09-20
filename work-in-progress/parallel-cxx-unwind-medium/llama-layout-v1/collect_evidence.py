from pathlib import Path
import hashlib
import json
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
inputs=['evidence/llama-native-link-20260910/llama-link.elf',
        'evidence/llama-native-link-20260910/result.json',
        'evidence/llama-native-link-20260910/unwind-audit.json',
        'board/kickpi_k7/scripts/dramboot.ld','board/kickpi_k7/README.md',
        'port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c',
        'port/new/nuttx/arch/arm64/src/rk3576/rk3576_model_arena.c',
        'port/new/nuttx/include/nuttx/mm/k7_model_arena.h',
        'artifacts/cxx-locale-20260910/.config','tools/verify_neon_file64_image.py',
        'tools/uart_load_cxx_unwind.py','tools/audit_k7_resources.py',
        'docs/DDR与eMMC资源接入_20260910.md','docs/独立DDR模型内存池_20260910.md']
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
commands=[[sys.executable,'-B','test_layout.py'],
          [sys.executable,'-B','audit_layout.py',str(ROOT/inputs[0])],
          ['readelf','-lW',str(ROOT/inputs[0])]]
records=[]
for cmd in commands:
    p=subprocess.run(cmd,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    records.append(dict(command=cmd,exit_code=p.returncode,output=p.stdout.decode('utf-8','replace')))
assert hashes=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
(HERE/'evidence.json').write_text(json.dumps(dict(input_sha256=hashes,commands=records,
    hardware_tested=False,sdk_accessed=False,formal_validator_modified=False),indent=2),encoding='utf-8')
print('commands passed:',all(r['exit_code']==0 for r in records))
