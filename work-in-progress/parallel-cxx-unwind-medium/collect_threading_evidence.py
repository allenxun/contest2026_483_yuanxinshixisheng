from pathlib import Path
import hashlib
import json
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
elf=ROOT/'artifacts/cxx-unwind-20260910/nuttx'
cmd=['readelf','-sW',str(elf)]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
lines=p.stdout.decode('utf-8','replace').splitlines()
tokens=['unseen_objects','seen_objects','object_mutex','registered_frames',
        '__cxa_get_globals','cxa_exception_storage','pthread_getspecific',
        'pthread_setspecific','pthread_once']
result={'command':cmd,'exit_code':p.returncode,
        'filtered_output':[l for l in lines if any(t in l for t in tokens)],
        'output_filter_tokens':tokens,'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
        'hardware_tested':False,
        'files_sha256':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
                        ['THREADING-RISK.md','integrated-audit.json','collect_threading_evidence.py']}}
(HERE/'threading-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
