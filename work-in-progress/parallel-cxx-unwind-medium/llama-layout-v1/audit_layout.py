"""Offline layout gate only: does not authorize a load or prove bootability."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BASE=0x40400000
RAM_END=0x48200000
CAP=BASE+8*1024*1024
MIN_HEAP_GAP=112*1024*1024  # Proposed policy, not measured application requirement.
RESERVED=[('dtb_firmware_conservative',0x48200000,0x49400000),
          ('radio_staging',0x50000000,0x50200000),
          ('loader_snapshot',0x51000000,0x51400000),
          ('model_arena',0x60000000,0xa0000000)]

def overlap(a,b,c,d): return a<d and c<b

def parse(path):
    data=Path(path).read_bytes()
    def u(fmt,off): return struct.unpack_from('<'+fmt,data,off)
    if data[:6]!=b'\x7fELF\x02\x01' or u('H',18)[0]!=183: raise ValueError('not LE ELF64 ARM64')
    entry,phoff,shoff=u('QQQ',24)
    phsize,phnum,shsize,shnum,shstr=u('HHHHH',54)
    if phsize!=56 or shsize!=64: raise ValueError('unexpected table entries')
    if phoff+phsize*phnum>len(data) or shoff+shsize*shnum>len(data): raise ValueError('truncated tables')
    loads=[]
    for i in range(phnum):
        t,flags,off,va,pa,fs,ms,align=u('IIQQQQQQ',phoff+i*phsize)
        loads.append(dict(type=t,flags=flags,offset=off,virtual=va,physical=pa,filesz=fs,memsz=ms,align=align))
    sections=[u('IIQQQQIIQQ',shoff+i*shsize) for i in range(shnum)]
    def blob(s): return data[s[4]:s[4]+s[5]]
    def string(table,n): return table[n:].split(b'\0',1)[0].decode('utf-8','replace')
    names=blob(sections[shstr]); symbols={}; allocated=[]
    for s in sections:
        if s[2]&2:
            allocated.append(dict(name=string(names,s[0]),address=s[3],size=s[5],type=s[1],flags=s[2]))
        if s[1]==2:
            strings=blob(sections[s[6]])
            for off in range(s[4],s[4]+s[5],s[9]):
                n,info,other,index,value,size=u('IBBHQQ',off)
                if index: symbols[string(strings,n)]=value
    header={}
    first=next((p for p in loads if p['physical']==entry and p['filesz']>=64),None)
    if first:
        offset,size,flags=u('QQQ',first['offset']+8)
        header=dict(text_offset=offset,image_size=size,flags=flags,magic=hex(u('I',first['offset']+56)[0]))
    return dict(entry=entry,elf_type=u('H',16)[0],file_bytes=len(data),loads=loads,
                symbols=symbols,allocated_sections=allocated,image_header=header,
                sha256=hashlib.sha256(data).hexdigest())

def validate(m,cap=CAP):
    errors=[]
    def require(ok,msg):
        if not ok: errors.append(msg)
    require(m['elf_type']==2 and m['entry']==BASE,'entry/type')
    loads=m['loads']; sy=m['symbols']
    require(len(loads)==3 and sorted(p['flags'] for p in loads)==[4,5,6],'three RX/R/RW loads')
    for p in loads:
        a=p['physical']; b=a+p['memsz']
        require(p['type']==1 and p['virtual']==a,'identity PT_LOAD')
        require(BASE<=a<=b<=RAM_END and b<=cap,'RAM/candidate memory cap')
        require(p['filesz']<=p['memsz'] and p['offset']+p['filesz']<=m['file_bytes'],'file containment')
        align=p['align']
        require(align in (0,1) or (align&(align-1)==0 and a%align==p['offset']%align),'alignment')
        require(not any(overlap(a,b,c,d) for _,c,d in RESERVED),'reserved overlap')
    for i,p in enumerate(loads):
        for q in loads[i+1:]:
            require(not overlap(p['physical'],p['physical']+p['memsz'],q['physical'],q['physical']+q['memsz']),'PT_LOAD overlap')
    pairs=[('_stext','_etext',5),('_srodata','_erodata',4),('_sdata','_e_initstack',6)]
    for lo,hi,flags in pairs:
        a=sy.get(lo,-1); b=sy.get(hi,-1)
        require(a>=BASE and b>a and any(p['physical']==a and p['physical']+p['memsz']==b and p['flags']==flags for p in loads),'symbol/PT_LOAD '+lo)
    order=['_sdata','_edata','_sbss','_ebss','_s_initstack','_e_initstack']
    values=[sy.get(n,-1) for n in order]
    require(all(x>=BASE for x in values) and values==sorted(values),'data/bss/stack ordering')
    end=max((p['physical']+p['memsz'] for p in loads),default=0)
    require(sy.get('g_idle_topstack')==end==sy.get('_e_initstack'),'stack/image end')
    require(RAM_END-end>=MIN_HEAP_GAP,'proposed 112MiB heap-gap floor')
    for s in m['allocated_sections']:
        require(any(p['physical']<=s['address'] and s['address']+s['size']<=p['physical']+p['memsz'] for p in loads),'allocated section containment '+s['name'])
    h=m['image_header']
    require(h.get('magic')=='0x644d5241' and h.get('text_offset')==0,'ARM64 header magic/offset')
    require(h.get('image_size')==end-BASE,'ARM64 image_size matches memory extent')
    return dict(layout_passed=not errors,errors=errors,entry=hex(BASE),memory_end=hex(end),
                memory_bytes=end-BASE,old_6MiB_gate_passed=end<=BASE+6*1024*1024,
                proposed_8MiB_headroom=cap-end,estimated_heap_gap=RAM_END-end,
                heap_gap_is_not_runtime_free_heap=True,boot_authorized=False,
                raw_binary_verified=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('elf'); p.add_argument('--output'); a=p.parse_args()
    model=parse(a.elf); result=validate(model)
    result.update(sha256=model['sha256'],elf_file_bytes=model['file_bytes'],loads=model['loads'],
                  image_header=model['image_header'],symbols={n:v for n,v in model['symbols'].items() if n in
                  ['__start','_stext','_etext','_srodata','_erodata','_sdata','_edata','_sbss','_ebss','_s_initstack','_e_initstack','g_idle_topstack','g_cpu_idlestackalloc']})
    result['raw_span_from_loads']=max(x['physical']+x['filesz'] for x in model['loads'])-BASE
    result['reserved']=RESERVED
    text=json.dumps(result,indent=2)
    if a.output: Path(a.output).write_text(text,encoding='utf-8')
    print(text)
    raise SystemExit(0 if result['layout_passed'] else 1)
