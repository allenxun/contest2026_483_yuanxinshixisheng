"""Extract unchanged candidate function bodies and compile with mock transport."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import re
from prepare import generate,function_span
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
generate()
candidate=HERE/'candidate/drivers/usbhost/usbhost_storage.c'
text=candidate.read_text(encoding='utf-8')
names=['usbhost_getle16','usbhost_getbe16','usbhost_getle32','usbhost_getbe32','usbhost_putle16','usbhost_putbe16','usbhost_putle32','usbhost_putbe32',
       'usbhost_requestsensecbw','usbhost_testunitreadycbw','usbhost_readcapacitycbw','usbhost_inquirycbw','usbhost_readcbw',
       'usbhost_cbwalloc','usbhost_bot_failed','usbhost_checked_command','usbhost_checked_capacity','usbhost_checked_read',
       'usbhost_testunitready','usbhost_requestsense','usbhost_readcapacity','usbhost_inquiry','usbhost_read','usbhost_write','usbhost_geometry']
chunks=[]; extraction=[]
for name in names:
    a,b=function_span(text,name); start=text.rfind('static',0,a)
    body=text[start:b]
    chunks.append(body)
    extraction.append(dict(name=name,start_line=text[:start].count('\n')+1,sha256=hashlib.sha256(body.encode('utf-8')).hexdigest()))
testfile=HERE/'mock-replay.c'
testfile.write_text('#define CONFIG_USBHOST_MSC_READONLY 1\n#include "mock-prefix.h"\n'+'\n\n'.join(chunks)+'\n#include "mock-tests.inc"\n',encoding='utf-8')
commands=[]
def run(command):
    p=subprocess.run(command,cwd=str(HERE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
    commands.append(dict(command=command,exit_code=p.returncode,output=p.stdout))
    print(p.stdout)
    if p.returncode:
        (HERE/'failed-run.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
        raise RuntimeError('check failed')
compiler=shutil.which('gcc')
run([compiler,'--version'])
run([compiler,'-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2',str(testfile),'-o',str(HERE/'mock-replay.exe')])
run([str(HERE/'mock-replay.exe')])
# Compare default-off preprocessor tokens with identical mocked header inputs.
# This proves preservation of these source branches, not target ABI/build.
default_outputs=[]
for label,body in [('original',(ROOT/'evidence/usb-storage-inputs-20260910/nuttx/drivers/usbhost/usbhost_storage.c').read_text(encoding='utf-8')),('candidate',text)]:
    stripped=re.sub(r'^\s*#\s*include[^\n]*', '',body,flags=re.M)
    p=HERE/('default-'+label+'.c'); p.write_text(stripped,encoding='utf-8')
    out=HERE/('default-'+label+'.i')
    run([compiler,'-E','-P','-DCONFIG_USBHOST=1','-DCONFIG_SCHED_WORKQUEUE=1','-DCONFIG_USBHOST_NPREALLOC=4',str(p),'-o',str(out)])
    default_outputs.append(re.findall(r'\w+|[^\s]',out.read_text(encoding='utf-8')))
assert default_outputs[0]==default_outputs[1], 'default-off token mismatch'
fixture=HERE/'patch-base'
for rel in ['drivers/usbhost/Kconfig','drivers/usbhost/usbhost_storage.c']:
    p=fixture/rel;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes((ROOT/'evidence/usb-storage-inputs-20260910/nuttx'/rel).read_bytes())
run(['git','apply','--check','--unsafe-paths','--directory='+fixture.as_posix(),str(HERE/'candidate.patch')])
def entry(p):
    data=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
inputs=[ROOT/'evidence/usb-storage-inputs-20260910/inputs.json',
        ROOT/'evidence/usb-storage-inputs-20260910/nuttx/drivers/usbhost/usbhost_storage.c',
        ROOT/'evidence/usb-storage-inputs-20260910/nuttx/drivers/usbhost/Kconfig',
        ROOT/'port/new/nuttx/drivers/usbhost/usbhost_xhci_rk3576.c']
(HERE/'run-evidence.json').write_text(json.dumps(dict(commands=commands,inputs=[entry(p) for p in inputs],
    candidate=entry(candidate),extracted_functions=extraction,
    default_off_tokens_equal=True,
    scope='real candidate function replay with mock ABI and transfer; not full NuttX TU or hardware'),indent=2)+'\n',encoding='utf-8')
(HERE/'delivery.json').write_text(json.dumps(dict(files=[entry(p) for p in sorted(HERE.rglob('*')) if p.is_file() and 'patch-base' not in p.parts and p.name!='delivery.json'],
    target_built=False,hardware_tested=False,patch_applied=False),indent=2)+'\n',encoding='utf-8')
