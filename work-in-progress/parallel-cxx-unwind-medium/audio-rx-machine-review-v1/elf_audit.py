"""Local ELF64/AArch64 byte audit; no cross-architecture disassembly."""
from pathlib import Path
import struct,json,hashlib
p=Path(__file__).resolve().parent;b=(p/'frozen-nuttx').read_bytes()
assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
shoff=struct.unpack_from('<Q',b,40)[0];shents,shnum,shstr=struct.unpack_from('<3H',b,58)
sections=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*shents) for i in range(shnum)]
def address(a,n):
 for s in sections:
  if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]:return b[s[4]+a-s[3]:s[4]+a-s[3]+n]
 raise ValueError(hex(a))
def string(a):
 out=bytearray()
 while address(a,1)!=b'\0':out+=address(a,1);a+=1
 return out.decode()
syms=[]
for s in sections:
 if s[1]!=2:continue
 strings=sections[s[6]];names=b[strings[4]:strings[4]+strings[5]]
 for o in range(s[4],s[4]+s[5],s[9]):
  ni,info,other,sect,val,size=struct.unpack_from('<IBBHQQ',b,o)
  name=names[ni:names.find(b'\0',ni)].decode()
  syms.append(dict(name=name,value=val,size=size,section=sect))
def symbol(n):return next(x for x in syms if x['name']==n)
m=symbol('g_mmu_regions');regions=[]
for i in range(m['size']//40):
 va,pa,size,name,attr=struct.unpack('<5Q',address(m['value']+40*i,40))
 regions.append(dict(va=hex(va),pa=hex(pa),size=hex(size),name=string(name),raw_attrs=hex(attr)))
cap=symbol('capture');assert cap['size']==96000*4
assert 0x40400000<=cap['value'] and cap['value']+cap['size']<=0x48200000
out=dict(elf_sha256=hashlib.sha256(b).hexdigest(),machine='AArch64',capture=cap,regions=regions)
(p/'elf-layout.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
