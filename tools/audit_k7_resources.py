"""Read-only FDT resource audit. Reports candidates, never authorizes RAM writes."""
import argparse, hashlib, json, struct
from pathlib import Path

def parse(data):
    if len(data)<40: raise ValueError("short header")
    magic,total,so,no,ro,ver,compat,cpu,ns,ss=struct.unpack_from(">10I",data)
    if magic!=0xd00dfeed or not 40<=total<=len(data): raise ValueError("header")
    if so<40 or no<40 or so+ss>total or no+ns>total: raise ValueError("bounds")
    names=data[no:no+ns];end=so+ss;stack=[];tree={};pos=so
    while pos+4<=end:
        token=struct.unpack_from(">I",data,pos)[0];pos+=4
        if token==1:
            stop=data.index(0,pos,end);stack.append(data[pos:stop].decode('ascii'));pos=(stop+4)&~3
            tree['/'.join(stack) or '/']={}
        elif token==2:
            if not stack: raise ValueError('node underflow')
            stack.pop()
        elif token==3:
            if not stack or pos+8>end: raise ValueError('property')
            length,offset=struct.unpack_from('>II',data,pos);pos+=8
            if offset>=ns or pos+length>end: raise ValueError('property bounds')
            stop=names.index(0,offset);key=names[offset:stop].decode('ascii')
            tree['/'.join(stack) or '/'][key]=data[pos:pos+length];pos=(pos+length+3)&~3
        elif token==4: pass
        elif token==9:
            if stack: raise ValueError('unclosed nodes')
            break
        else: raise ValueError('token')
    else: raise ValueError('missing end')
    if ro<40 or ro%8: raise ValueError('reserve offset')
    reserves=[]
    while ro+16<=total:
        start,size=struct.unpack_from('>QQ',data,ro);ro+=16
        if not start and not size:break
        if size:reserves.append(span(start,size))
    else: raise ValueError('reserve terminator')
    return tree,reserves

def span(start,size):
    if start<0 or size<=0 or start+size>1<<64:raise ValueError('range')
    return dict(start=start,end=start+size,bytes=size)

def ranges(raw,ac,sc):
    if ac not in (1,2) or sc not in (1,2):raise ValueError('cell width')
    stride=4*(ac+sc)
    if len(raw)%stride:raise ValueError('reg length')
    out=[]
    for p in range(0,len(raw),stride):
        start=int.from_bytes(raw[p:p+4*ac],'big');size=int.from_bytes(raw[p+4*ac:p+stride],'big')
        if size:out.append(span(start,size))
    return out

def subtract(banks,excluded):
    result=[]
    for bank in banks:
        parts=[(bank['start'],bank['end'])]
        for x in excluded:
            nxt=[]
            for a,b in parts:
                if x['end']<=a or x['start']>=b:nxt.append((a,b));continue
                if a<x['start']:nxt.append((a,x['start']))
                if x['end']<b:nxt.append((x['end'],b))
            parts=nxt
        result.extend(span(a,b-a) for a,b in parts)
    return result

def audit(path):
    data=Path(path).read_bytes();tree,excluded=parse(data)
    def cells(node,key,default):return int.from_bytes(tree.get(node,{}).get(key,default.to_bytes(4,'big')),'big')
    ac=cells('/','#address-cells',2);sc=cells('/','#size-cells',1);banks=[]
    for name,props in tree.items():
        if props.get('device_type')==b'memory\0':banks+=ranges(props.get('reg',b''),ac,sc)
    for a,b in zip(sorted(banks,key=lambda x:x['start']),sorted(banks,key=lambda x:x['start'])[1:]):
        if a['end']>b['start']:raise ValueError('overlapping banks')
    rac=cells('/reserved-memory','#address-cells',ac);rsc=cells('/reserved-memory','#size-cells',sc)
    dynamic=[]
    for name,props in tree.items():
        if name.startswith('/reserved-memory/'):
            excluded+=ranges(props.get('reg',b''),rac,rsc)
            if 'size' in props and 'reg' not in props:dynamic.append(name)
    # Historical K7 handoff reservations. Not a replacement for current bdinfo.
    fixed=[(0x40200000,0x48200000,'existing image/heap'),(0x48200000,0x49400000,'DTB and firmware gap'),
           (0x50000000,0x50200000,'radio staging'),(0x51000000,0x51400000,'loader snapshot'),
           (0xfb000000,0x100000000,'conservative U-Boot high exclusion')]
    excluded += [dict(span(a,b-a),reason=why) for a,b,why in fixed]
    emmc=tree.get('/mmc@2a330000',{})
    return dict(source=str(path),sha256=hashlib.sha256(data).hexdigest(),memory_banks=banks,
        described_bytes=sum(x['bytes'] for x in banks),exclusions=excluded,dynamic_reservations=dynamic,
        candidate_ranges=subtract(banks,excluded),activation_allowed=False,
        reason='Archived DTB and conservative exclusions only; current handoff, DMA and allocator checks required',
        emmc=dict(compatible=emmc.get('compatible',b'').decode().strip('\0').split('\0'),
                  registers=ranges(emmc.get('reg',b''),ac,sc),bus_width=int.from_bytes(emmc.get('bus-width',b''),'big')))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('dtb',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    report=audit(a.dtb);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
