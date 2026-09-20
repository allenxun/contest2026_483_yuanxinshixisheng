"""Read-only CRC bisection, at most 256 checks; never changes board RAM."""
import hashlib,json,re,time
from pathlib import Path
import serial,zlib
root=Path(__file__).resolve().parent
data=Path('/home/swl/openvela/work/native-asr-model-session/decoder.ort').read_bytes()
assert hashlib.sha256(data).hexdigest()=='0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14'
stamp=time.strftime('%Y%m%d-%H%M%S');log=(root/('locate-'+stamp+'.log')).open('xb')
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2);s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
checks=0;bad=[]
def compare(offset,n):
 global checks
 checks+=1
 assert checks<=256,'CRC check budget exceeded'
 s.write(('crc32 %x %x\r'%(0x8a000000+offset,n)).encode());raw=bytearray();end=time.monotonic()+12
 while time.monotonic()<end:
  raw.extend(s.read(4096))
  if re.search(rb'(?:^|\n)=> $',raw):break
 log.write(raw);log.flush()
 m=re.search(rb'==>\s+([0-9a-fA-F]{8})',raw);assert m,'Missing CRC'
 expected=zlib.crc32(data[offset:offset+n])&0xffffffff
 if int(m[1],16)==expected:return
 if n<=64:bad.append({'offset':offset,'bytes':n,'address':hex(0x8a000000+offset)});return
 half=(n//2)//4*4
 compare(offset,half);compare(offset+half,n-half)
try:
 compare(0,len(data))
 result={'checks':checks,'changed_ranges':bad,'covered_bytes':sum(x['bytes'] for x in bad),'read_only':True}
 (root/'decoder-change.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
finally:s.close();log.close()
