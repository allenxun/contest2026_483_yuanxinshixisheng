from pathlib import Path
import hashlib
import json
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
cmd=['readelf','--debug-dump=macro',str(ROOT/'artifacts/eh-control-20260910/nuttx')]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
text=p.stdout.decode('utf-8','replace')
tokens=['K7EH_HOST_TEST','K7EH_SLOW_READY','K7EH_BAD_COUNT']
result=dict(command=cmd,exit_code=p.returncode,full_output_sha256=hashlib.sha256(p.stdout).hexdigest(),
    relevant_lines=[s for s in text.splitlines() if 'K7EH' in s or '__NuttX__' in s or 'main k7ehcontrol_main' in s],
    unwanted_macro_mentions={s:s in text for s in tokens},
    note='ELF debug macro evidence; exact compile-command/preprocessing confirmation requested separately')
(HERE/'macro-scan.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
