"""Reproduce local tests and freeze evidence without touching old deliveries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
def digest(p):
    data=p.read_bytes()
    return dict(path=str(p),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))

command=[sys.executable,'-B',str(HERE/'test_accept_output.py')]
proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
(HERE/'run-evidence.json').write_text(json.dumps(dict(command=command,exit_code=proc.returncode,output=proc.stdout,hardware_tested=False),indent=2)+'\n',encoding='utf-8')
inputs=[HERE.parent/'eh-control-v1'/'host-results.json',HERE.parent/'eh-control-v1'/'k7ehcontrol_main.cxx']
delivery=dict(scope='offline host parser validation only',inputs=[digest(p) for p in inputs],
              files=[digest(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='delivery.json'],
              tests_passed=proc.returncode==0,hardware_tested=False)
(HERE/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf-8')
print(proc.stdout)
sys.exit(proc.returncode)
