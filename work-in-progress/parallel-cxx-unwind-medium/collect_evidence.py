"""Run only local read-only checks and save evidence in this directory."""
from pathlib import Path
import subprocess
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
commands=[
    [sys.executable,'-B',str(HERE/'test_audit_elf.py')],
    [sys.executable,'-B',str(HERE/'audit_elf.py'),str(ROOT/'artifacts/cxx-tls-20260910/nuttx')],
    ['git','apply','--check','--ignore-space-change',str(HERE/'candidate.patch')],
    ['readelf','-SW',str(ROOT/'artifacts/cxx-tls-20260910/nuttx')],
    ['readelf','-p','.comment',str(ROOT/'artifacts/cxx-tls-20260910/nuttx')],
    ['objdump','-d','--disassemble=lib_cxx_initialize',str(ROOT/'artifacts/cxx-tls-20260910/nuttx')]]
records=[]
for cmd in commands:
    proc=subprocess.run(cmd,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    records.append({'command':cmd,'exit_code':proc.returncode,'output':proc.stdout.decode('utf-8','replace')})
inputs={}
for rel in ['README.md','project-manifest.json','docs/代码日志对应表.md','app/k7cxx/k7cxx_main.cxx',
            'board/kickpi_k7/CMakeLists.txt','board/kickpi_k7/src/CMakeLists.txt',
            'board/kickpi_k7/scripts/dramboot.ld','board/kickpi_k7/src/kickpi_k7_appinit.c',
            'artifacts/cxx-tls-20260910/nuttx','artifacts/cxx-tls-20260910/.config']:
    inputs[rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir()
         if p.is_file() and p.name!='run-evidence.json'}
(HERE/'run-evidence.json').write_text(json.dumps({'commands':records,'input_sha256':inputs,
    'output_sha256':outputs,'candidate_compiled':False,'hardware_tested':False},indent=2),encoding='utf-8')
print('Recorded {} commands and {} output hashes'.format(len(records),len(outputs)))
