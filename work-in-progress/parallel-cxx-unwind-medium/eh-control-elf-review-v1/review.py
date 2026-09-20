import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
build=ROOT/'artifacts/eh-control-20260910'
report_path=ROOT/'evidence/build/eh-control-20260910/verification.json'
report=json.loads(report_path.read_text())
data=(build/'nuttx').read_bytes(); binary=(build/'nuttx.bin').read_bytes()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def u(fmt,off): return struct.unpack_from('<'+fmt,data,off)
phoff=u('Q',32)[0]; step,count=u('HH',54)
loads=[u('IIQQQQQQ',phoff+i*step) for i in range(count)]
def readva(address,size):
    for p in loads:
        if p[0]==1 and p[3]<=address and address+size<=p[3]+p[5]:
            return data[p[2]+address-p[3]:p[2]+address-p[3]+size]
    raise ValueError('not in file-backed load')
cmd=['readelf','-sW',str(build/'nuttx')]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
text=p.stdout.decode('utf-8','replace')
(HERE/'symbols.txt').write_text(text,encoding='utf-8')
symbols={}
for line in text.splitlines():
    m=re.match(r'\s*\d+: ([0-9a-f]+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(.+)',line)
    if m and m[3]!='UND': symbols[m[4]]=(int(m[1],16),int(m[2]))
base,size=symbols['g_builtins']; entries=[]
for off in range(0,size,24):
    name,priority,stack,entry=struct.unpack('<QiiQ',readva(base+off,24))
    if entry==symbols['k7ehcontrol_main'][0]:
        entries.append(dict(record_address=hex(base+off),name_bytes=readva(name,12).hex(),priority=priority,stack=stack,entry=hex(entry)))
allocated=b''.join(data[p[2]:p[2]+p[5]] for p in loads if p[0]==1)
strings=[b'single\0',b'warm1\0',b'K7EHCONTROL PREHEAT_PASS caught=1 cleaned=3 workers_created=0\0',
         b'usage: k7ehcontrol single|warm1 (fresh boot each; single CPU5, warm1 CPU4/5)\0']
inputs=[report_path,ROOT/'app/k7ehcontrol/k7ehcontrol_main.cxx',
        HERE.parent/'eh-control-v1/k7ehcontrol_main.cxx']
result={'artifact_checks':{name:len((build/name).read_bytes())==item['bytes'] and sha(build/name)==item['sha256'] for name,item in report['artifacts'].items()},
        'source_hash':sha(inputs[1]),'frozen_source_matches':sha(inputs[1])==sha(inputs[2])==report['sources']['app/k7ehcontrol/k7ehcontrol_main.cxx'],
        'load_bytes_match_bin':all(binary[x[4]-0x40400000:x[4]-0x40400000+x[5]]==data[x[2]:x[2]+x[5]] for x in loads if x[0]==1),
        'entry_symbol':symbols['k7ehcontrol_main'],'builtin_records_interpreted_QiiQ':entries,
        'allocated_strings':{s.decode('utf-8').rstrip('\0'):s in allocated for s in strings},
        'host_main_symbol_present':'main' in symbols,'macro_exclusion_proven_by_symbols_alone':False,
        'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in inputs},
        'elf_sha256':sha(build/'nuttx'),'hardware_tested':False}
(HERE/'review.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
