"""Report only the last CRC region/address; never emit RAM command payloads."""
import json,re
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'evidence/phone-pairing-20260909/ramload.bin'
with p.open('rb') as f:
    f.seek(max(0,p.stat().st_size-65536));tail=f.read()
matches=list(re.finditer(rb'crc32 ([0-9a-f]+) ([0-9a-f]+)',tail))
result=dict(log_bytes=p.stat().st_size)
if matches:
    addr,size=[int(v,16) for v in matches[-1].groups()]
    result.update(crc_address=hex(addr),bytes=size)
    if 0x40400000<=addr<0x40600000:
        result['image_progress_percent']=round(100*(addr-0x40400000)/1915896,1)
print(json.dumps(result))
