"""Verify this immutable Add image against real low-bank and live-DTB bounds."""
import hashlib,json,struct,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'work-in-progress/parallel-cxx-unwind-medium'))
from audit_elf import audit
REV='voice-ort-trace-20260911'
def verify(build):
 build=Path(build).resolve();assert build==R/'artifacts'/REV
 report=json.loads((R/'evidence/build'/REV/'verification.json').read_text())
 assert report['build_exit_code']==0
 for rel,digest in report['sources'].items():assert hashlib.sha256((R/rel).read_bytes()).hexdigest()==digest
 for n,v in report['artifacts'].items():
  b=(build/n).read_bytes();assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
 saved=R/'evidence/build'/REV/'image-audit.json'
 if saved.exists():
  unwind=json.loads(saved.read_text())['unwind']
  assert unwind['sha256']==report['artifacts']['nuttx']['sha256']
 else:unwind=audit(build/'nuttx')
 assert unwind['passed'],unwind
 data=(build/'nuttx').read_bytes();binary=(build/'nuttx.bin').read_bytes()
 assert data[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',data,18)[0]==183
 entry,phoff=struct.unpack_from('<QQ',data,24);step,count=struct.unpack_from('<HH',data,54)
 assert entry==0x40400000 and step==56 and count==3
 config=dict(line.split('=',1) for line in (build/'.config').read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)
 assert int(config['CONFIG_RAM_START'],0)==entry
 ram_end=entry+int(config['CONFIG_RAM_SIZE'],0)
 assert ram_end==0x48200000 and ram_end<0x48300000<0x48400000
 for key in ('CONFIG_EXAMPLES_K7VOICE','CONFIG_EXAMPLES_K7RADIO_SHARED','CONFIG_CXX_EXCEPTION','CONFIG_BOARDCTL_RESET'):
  assert config[key]=='y'
 segments=[]
 for i in range(count):
  kind,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',data,phoff+i*step)
  assert kind==1 and flags in (4,5,6) and va==pa and fs<=ms
  assert entry<=pa and pa+ms<ram_end and off+fs<=len(data)
  assert pa-entry+fs<=len(binary) and binary[pa-entry:pa-entry+fs]==data[off:off+fs]
  segments.append(dict(start=pa,end=pa+ms,filesz=fs))
 assert all(a['end']<=b['start'] for a,b in zip(segments,segments[1:]))
 image_end=max(p['end'] for p in segments)
 assert binary[56:60]==b'ARM\x64'
 text_offset,image_size=struct.unpack_from('<QQ',binary,8)
 assert text_offset==0 and image_size==image_end-entry
 assert 0<len(binary)<image_size and len(binary)%8==0
 return dict(entry=hex(entry),memory_end=hex(image_end),memory_bytes=image_size,ram_end=hex(ram_end),
             sha256=hashlib.sha256(binary).hexdigest(),unwind=unwind,hardware_tested=False)
if __name__=='__main__':
 result=verify(R/'artifacts'/REV)
 (R/'evidence/build'/REV/'image-audit.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
