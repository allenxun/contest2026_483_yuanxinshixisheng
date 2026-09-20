"""Read-only ELF/config/source binding. Prints command; does not run it."""
import pathlib,struct,json,hashlib,sys
P=pathlib.Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def bind(elf,verification,sdk):
 b=pathlib.Path(elf).read_bytes()
 if len(b)>64*1024*1024:raise ValueError('ELF over64MiB')
 v=json.loads(pathlib.Path(verification).read_text(encoding='utf-8-sig'));sdk=pathlib.Path(sdk)
 assert v['build_exit_code']==0 and sha(b)==v['artifacts']['nuttx']['sha256']
 assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
 config=(sdk/'config').read_bytes();assert sha(config)==v['artifacts']['.config']['sha256']
 for line in [b'CONFIG_ARM64_VA_BITS=48',b'CONFIG_ARM64_PA_BITS=48',b'CONFIG_ARM64_MAX_XLAT_TABLES=20',b'CONFIG_RAM_START=0x40400000',b'CONFIG_RAM_SIZE=132120576']:
  assert line in config.splitlines(),line
 reviewed=json.loads((P/'input/evidence/audio-mmu-input-20260910/inputs.json').read_text(encoding='utf-8-sig'))
 sdk_hashes={}
 for row in reviewed:
  if row['file'] in ('arm64_mmu.c','arm64_mmu.h','arm64_arch.h','rk3576_boot.c'):
   data=(sdk/row['file']).read_bytes();assert sha(data)==row['sha256'];sdk_hashes[row['file']]=sha(data)
 key='port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c'
 assert v['sources'][key]==sdk_hashes['rk3576_boot.c']
 shoff=struct.unpack_from('<Q',b,40)[0];ents,n,si=struct.unpack_from('<3H',b,58)
 assert ents==64 and 0<n<=4096 and shoff+n*64<=len(b)
 secs=[struct.unpack_from('<IIQQQQIIQQ',b,shoff+i*64) for i in range(n)]
 def addr(a,size):
  for s in secs:
   if s[1]!=8 and s[3]<=a and a+size<=s[3]+s[5]:
    off=s[4]+a-s[3];assert off+size<=len(b);return b[off:off+size]
  raise ValueError('address not file-backed')
 symbols={}
 for s in secs:
  if s[1]!=2:continue
  assert s[9]==24 and s[5]%24==0 and s[4]+s[5]<=len(b) and s[6]<n
  z=secs[s[6]];names=b[z[4]:z[4]+z[5]]
  for off in range(s[4],s[4]+s[5],24):
   ni,info,other,sect,val,size=struct.unpack_from('<IBBHQQ',b,off)
   end=names.find(b'\0',ni);assert 0<=ni<len(names) and end>=ni
   name=names[ni:end].decode('ascii')
   if name in ('xlat_tables','base_xlat_table','g_mmu_regions'):
    assert name not in symbols and 0<sect<n
    symbols[name]=(val,size,sect)
 x=symbols['xlat_tables'];r=symbols['base_xlat_table']
 for item,size in [(x,81920),(r,4096)]:
  a,s,section=item;assert s==size and not a%4096 and 0x40400000<=a<a+s<=0x48200000
  sec=secs[section];assert sec[1]==8 and sec[2]&2 and sec[3]<=a and a+s<=sec[3]+sec[5]
 assert x[0]+x[1]<=r[0] or r[0]+r[1]<=x[0]
 m=symbols['g_mmu_regions'];assert m[1]%40==0 and m[1]<=40*64
 regions=[struct.unpack('<4QI4x',addr(m[0]+i,40)) for i in range(0,m[1],40)]
 for a,size,attr in [(x[0],x[1],12),(r[0],r[1],12),(0x2a610000,4,8)]:
  hits=[z for z in regions if z[1]<a+size and a<z[1]+z[2]]
  assert len(hits)==1
  pa,va,sz,name,flags=hits[0]
  assert va<=a and a+size<=va+sz and pa==va and flags==attr
 return dict(elf_sha256=sha(b),config_sha256=sha(config),reviewed_sdk=sdk_hashes,
  xlat=dict(begin=hex(x[0]),end=hex(x[0]+x[1])),base=dict(begin=hex(r[0]),end=hex(r[0]+r[1])),
  command='k7sound mmu 0x%x 0x%x'%(x[0],r[0]),
  scope='Structural ELF and supplied source binding; operator must match loaded ELF. Does not attest SDK compilation independently.')
if __name__=='__main__':
 if len(sys.argv)!=4:raise SystemExit('usage: bind_elf.py ELF verification.json exact-sdk-input-dir')
 print(json.dumps(bind(*sys.argv[1:]),indent=2))
