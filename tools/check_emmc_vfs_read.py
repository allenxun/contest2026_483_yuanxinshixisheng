"""Discard a bounded read of 64KiB from the read-only user-area block device."""
import json,re,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/emmc-block-20260910'
sys.path.insert(0,str(R.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
prior=json.loads((E/'blockcheck-01.json').read_text())
assert prior['prompt_returned'] and any('EMMC blockcheck rc=0' in x for x in prior['lines'])
dest=E/'vfs-read.json';assert not dest.exists()
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2)
s.dtr=False;s.rts=False;s.port='COM8';records=[]
with s:
    for cmd in ('dd if=/dev/emmc0ro of=/dev/null bs=512 count=128','k7emmc gpt'):
        start=time.monotonic();s.write(cmd.encode('ascii')+b'\r');s.flush();buf=bytearray();returned=False
        while time.monotonic()-start<10:
            buf.extend(s.read(8192))
            if re.search(rb'nsh>\s*(?:\x1b\[K)?$',buf):returned=True;break
        lines=[]
        for line in buf.decode('ascii',errors='replace').splitlines():
            line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
            if line.startswith(('dd:','nsh:','EMMC ','ERROR:')) or re.match(r'^\d+.*(?:records|bytes)',line):lines.append(line)
        records.append(dict(command=cmd,elapsed_seconds=time.monotonic()-start,prompt_returned=returned,lines=lines))
        if not returned:break
dest.write_text(json.dumps(dict(records=records,requested_read_bytes=65536,destination='/dev/null',storage_writes=False),indent=2)+'\n',encoding='utf-8')
print(json.dumps(records))
