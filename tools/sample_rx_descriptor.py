"""Bounded read-only RAM descriptor sampling; persist no raw RAM or payload.

Requires the exact AMSDU image. NSH xd samples are asynchronous and cannot
prove frame coherence; they only guide subsequent validated driver changes.
"""
import argparse,hashlib,json,re,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'无线适配_2026-09-08/tools/pydeps'))
import serial
p=argparse.ArgumentParser();p.add_argument('--log',type=Path,required=True);a=p.parse_args()
assert hashlib.sha256((ROOT/'artifacts/wifi-amsdu-20260909/nuttx.bin').read_bytes()).hexdigest()=='fe7db9d49c68b4274b123362a8c90e63be31a0f7ab2caaeb9435c27147a4fd59'
sym=(ROOT/'artifacts/wifi-amsdu-20260909/System.map').read_text()
assert re.search(r'^00000000408f6bf0 b g_rx$',sym,re.M)
s=serial.Serial(port=None,baudrate=1500000,timeout=.01,write_timeout=2,rtscts=False,dsrdtr=False,xonxoff=False)
s.rts=False;s.dtr=False;s.port='COM8'
def cmd(command):
 s.write(command.encode('ascii')+b'\r');s.flush();data=bytearray();deadline=time.monotonic()+2
 while time.monotonic()<deadline:
  data.extend(s.read(4096))
  if re.search(rb'nsh>\s*(?:\x1b\[K)?$',data):break
 # Never print or store data: it may contain unrelated asynchronous frames.
 return data
seen=set();counts={}
with s,a.log.open('x',encoding='utf-8') as log:
 reply=cmd('arp -i wlan0 -d 10.3.0.1')
 print('ARP reset command error='+str(b'ERROR' in reply or b'failed' in reply),flush=True)
 cmd('ping -c 20 -I wlan0 10.3.0.1 &')
 deadline=time.monotonic()+25
 while time.monotonic()<deadline:
  for slot in range(6):
   raw=cmd(f'xd {0x408f6bf0+slot*1536:x} 20')
   values=[]
   for line in raw.splitlines():
    m=re.match(rb'^(?:0000|0010): ((?:[0-9a-f]{2} ){1,16})',line)
    if m:values.extend(int(v,16) for v in m[1].split())
   category='parsed20' if len(values)==20 else 'parse_failed'
   counts[category]=counts.get(category,0)+1
   if len(values)!=20 or values[3]!=7:continue
   counts['channel7']=counts.get('channel7',0)+1
   if not(values[4]&8):continue
   d=values;key=tuple(d)
   if key in seen:continue
   seen.add(key)
   # Metadata only, no PN, Ethernet payload, keys or credentials.
   row=dict(time=datetime.now(timezone.utc).isoformat(),slot=slot,wire=d[0]+256*d[1]+4,header_flags=d[2],flags=d[4],sequence=(d[8]+256*d[9])&4095,meta=d[10]+256*d[11],offset=d[18],index=d[19]&63,lastbyte=d[19],length=d[16]+256*d[17]+6)
   log.write(json.dumps(row)+'\n');log.flush();print(json.dumps(row),flush=True)
print('Read-only sampling complete; samples may race RX and are not acceptance evidence',counts)
