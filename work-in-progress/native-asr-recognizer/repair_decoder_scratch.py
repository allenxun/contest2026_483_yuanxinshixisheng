"""Restore only 276 CRC-localized scratch bytes, then verify whole decoder."""
import hashlib,json,re,struct,time
from pathlib import Path
import serial
root=Path(__file__).resolve().parent
data=Path('/home/swl/openvela/work/native-asr-model-session/decoder.ort').read_bytes()
assert hashlib.sha256(data).hexdigest()=='0f58ca4bd77728d8e512b852eff58e9aeedd90cfa2016ae40379b4700a78da14'
ranges=json.loads((root/'decoder-change.json').read_text())['changed_ranges']
assert sum(x['bytes'] for x in ranges)==276
assert [(x['offset'],x['bytes']) for x in ranges]==[(41943164,36),(41943200,36),(67109028,32),(67109060,36),(67109096,32),(71303268,36),(71303304,36),(71303340,32)]
stamp=time.strftime('%Y%m%d-%H%M%S');log=(root/('scratch-repair-'+stamp+'.log')).open('xb')
s=serial.Serial(port=None,baudrate=1500000,timeout=.02,write_timeout=2);s.dtr=False;s.rts=False;s.port='/dev/ttyUSB0';s.open()
def cmd(text):
 s.write(text.encode());raw=bytearray();end=time.monotonic()+20
 while time.monotonic()<end:
  raw.extend(s.read(4096))
  if re.search(rb'(?:^|\n)=> $',raw):break
 log.write(raw);log.flush();assert re.search(rb'(?:^|\n)=> $',raw)
 assert b'Unknown command' not in raw and b'Usage:' not in raw
 return bytes(raw)
try:
 assert b'==> 60da1369' in cmd('crc32 8a000000 44b0310\r')
 for item in ranges:
  for offset in range(item['offset'],item['offset']+item['bytes'],4):
   value=struct.unpack_from('<I',data,offset)[0]
   cmd('mw.l %x %x 1\r'%(0x8a000000+offset,value))
 assert b'==> 2af64aa7' in cmd('crc32 8a000000 44b0310\r')
 assert b'==> b5f7ae2d' in cmd('crc32 86000000 3e7da30\r')
 print('PASS 276 scratch bytes restored; complete decoder and encoder tail CRC verified',flush=True)
 s.write(b'fastboot usb 1\r');time.sleep(2);log.write(s.read(4096));log.flush()
finally:s.close();log.close()
