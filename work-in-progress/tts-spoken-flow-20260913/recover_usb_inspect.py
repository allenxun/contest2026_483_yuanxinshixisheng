"""Repeat the recorded board reset recovery; inspect, do not repair, ROMFS."""
import sys,json,hashlib,zlib,re
from pathlib import Path
here=Path(__file__).resolve().parent
sys.argv=[sys.argv[0],'usb-recovery-inspect']
scope={'__file__':str(here/'load_prefix.py')}
source=(here/'load_prefix.py').read_text()
exec(compile(source.split('\ntry:\n',1)[0],str(here/'load_prefix.py'),'exec'),scope)
image=Path('/home/swl/openvela/work/parallel-offline-tts-20260913/k7tts.romfs').read_bytes()
assert hashlib.sha256(image).hexdigest()=='8b30719c6a7d1b424676bb1b6ea950b1dfdeeeb0601531c8e49742d0387a7c0f'
base=0x96000000
try:
  with scope['open_port']() as port:
    port.write(b'\x03\r');port.flush()
    assert re.search(rb'(?:^|\n)=>\s*$',scope['read'](port,5,rb'(?:^|\n)=>\s*$'))
    scope['check_crc'](port,0x90000000,0x44b0310,'2af64aa7')
    scope['check_crc'](port,0x86000000,0x3e7da30,'b5f7ae2d')
    scope['reset_to_uboot'](port)
    scope['check_crc'](port,0x90000000,0x44b0310,'2af64aa7')
    scope['check_crc'](port,0x86000000,0x3e7da30,'b5f7ae2d')
    stack=[(0,len(image))];bad=[];queries=0
    while stack:
      offset,size=stack.pop();queries+=1
      if queries>160:raise RuntimeError('Inspection bound reached; no repair writes')
      out=scope['command'](port,'crc32 %x %x'%(base+offset,size),30)
      match=re.search(rb'==>\s+([0-9a-f]{8})',out)
      assert match
      expected=zlib.crc32(image[offset:offset+size])&0xffffffff
      if int(match[1],16)==expected:continue
      if size<=64:
        bad.append({'offset':offset,'size':size,'actual_crc32':match[1].decode(),'expected_crc32':'%08x'%expected})
        if sum(x['size'] for x in bad)>4096:raise RuntimeError('More than4KiB changed; no repair writes')
      else:
        half=(size//2)//4*4
        stack.extend([(offset+half,size-half),(offset,half)])
    (here/'rom-reset-differences.json').write_text(json.dumps({'queries':queries,'bytes':sum(x['size'] for x in bad),'blocks':bad},indent=2))
    print('ROMFS changed bytes bounded:',sum(x['size'] for x in bad))
finally:
  scope['LOG'].close()
