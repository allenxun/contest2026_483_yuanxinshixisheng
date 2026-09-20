"""Freeze this directory's host test evidence only; original source not altered."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
command=[sys.executable,'-B',str(HERE/'test_acceptance.py')]
p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
(HERE/'run-evidence.json').write_text(json.dumps(dict(command=command,exit_code=p.returncode,output=p.stdout,target_tested=False),indent=2)+'\n',encoding='utf-8')
def entry(path):
    data=path.read_bytes();return dict(path=str(path.relative_to(HERE)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
(HERE/'delivery.json').write_text(json.dumps(dict(files=[entry(path) for path in sorted(HERE.rglob('*')) if path.is_file() and path.name!='delivery.json'],
    all_tests_passed=p.returncode==0,scope='offline parser; synthetic tests; frozen source contract'),indent=2)+'\n',encoding='utf-8')
print(p.stdout);raise SystemExit(p.returncode)
