"""Compile the same deterministic integer workload at O0/O2; preserve evidence."""
import hashlib
import json
import subprocess
from pathlib import Path
R = Path(__file__).resolve().parents[1]
E = R / 'evidence/k7load-host-20260910'
E.mkdir(exist_ok=True)
assert not (E / 'result.json').exists()
src = E / 'test.c'
src.write_text('#include <stdio.h>\n#include "workload.h"\nint main(void) { for (unsigned i=0;i<100;i++) if(k7load_batch()!=K7LOAD_EXPECTED) return 1; puts("100 batches matched reference"); return 0; }\n')
records = []
for opt in ['O0', 'O2']:
    output = E / (opt + '.exe')
    for label, command in [('compile', [r'D:\software\mingw64\mingw64\bin\gcc.exe', '-std=c11', '-' + opt, '-Wall', '-Wextra', '-Werror', '-I' + str(R / 'app/k7load'), str(src), '-o', str(output)]), ('run', [str(output)])]:
        result = subprocess.run(command, capture_output=True, timeout=30)
        (E / (opt + '-' + label + '.stdout')).write_bytes(result.stdout)
        (E / (opt + '-' + label + '.stderr')).write_bytes(result.stderr)
        records.append(dict(optimization=opt, stage=label, argv=command, exit_code=result.returncode))
        if result.returncode:
            (E / 'result.json').write_text(json.dumps(dict(passed=False, records=records), indent=2))
            raise RuntimeError('Workload check failed')
(E / 'result.json').write_text(json.dumps(dict(passed=True, records=records,
    workload_sha256=hashlib.sha256((R / 'app/k7load/workload.h').read_bytes()).hexdigest(),
    reference='Python uint32 xorshift13/17/5, seed 0x12345678, 4096 steps -> 0xf6e37410',
    scope='Workload integer reference only; not target scheduling or radio'), indent=2))
print('PASS O0/O2, 100 checked batches each')
