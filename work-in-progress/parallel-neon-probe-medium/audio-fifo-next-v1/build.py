import pathlib,hashlib,json,difflib,subprocess
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['app/k7sound/duplex.c','app/k7sound/duplex.h','app/k7sound/input/rockchip_sai.h',
 'evidence/audio-marker-20260910/k7sound-loopback-numbered-20260910-215239.bin',
 'evidence/audio-marker-20260910/numbered-analysis.json',
 'evidence/audio-sai-trm-20260910/SAI-layout.txt',
 'work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.c']
items=[]
for n in names:
 b=(root/n).read_bytes();d=p/'input'/n;d.parent.mkdir(parents=True,exist_ok=True)
 if d.exists():assert d.read_bytes()==b,'frozen input changed'
 else:d.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
c=p/'candidate';(c/'input').mkdir(parents=True,exist_ok=True)
(c/'input/rockchip_sai.h').write_bytes((p/'input'/names[2]).read_bytes())
oldc=(p/'input'/names[0]).read_text();oldh=(p/'input'/names[1]).read_text()
t=oldc.replace('int route,int numbered,struct dl_result*r)', 'int route,int numbered,unsigned rx_lanes,struct dl_result*r)',1)
t=t.replace('uint32_t v,t,x,mask,value,pathmask;', 'uint32_t v,t,x,mask,value,rxvalue,pathmask;',1)
t=t.replace('path_saved=0;', 'path_saved=0,rx_saved=0;',1)
t=t.replace('memset(r,0,sizeof(*r));','memset(r,0,sizeof(*r));\n if(rx_lanes!=1&&rx_lanes!=2)return r->result=-22;\n if(rx_lanes==2&&(!numbered||frames!=128||route!=DL_ROUTE_DEFAULT))return r->result=-22;',1)
t=t.replace('path_saved=1;r->held=1;', 'if(rx_lanes==2){\n  if(rd(p,SAI_RXCR,&r->rxcr_before))return r->result=-5;\n  rx_saved=1;\n }\n path_saved=1;r->held=1;',1)
t=t.replace('if(mod(p,SAI_TXCR,mask,value)||mod(p,SAI_RXCR,mask,value)||',
 'rxvalue=(value&~SAI_XCR_CSR_MASK)|SAI_XCR_CSR(rx_lanes);\n if(mod(p,SAI_TXCR,mask,value)||mod(p,SAI_RXCR,mask,rxvalue)||',1)
t=t.replace('expect(p,SAI_RXCR,mask,value)', 'expect(p,SAI_RXCR,mask,rxvalue)',1)
t=t.replace('if((rc=delay20(p)))goto done;', 'if(rx_lanes==2&&rd(p,SAI_RXCR,&r->rxcr_active))goto done;\n if((rc=delay20(p)))goto done;',1)
t=t.replace('if(!r->stop_rc&&!r->restore_rc&&!r->amp_rc)r->held=0;', '''if(!r->stop_rc&&rx_saved){
  r->rx_restore_rc=mod(p,SAI_RXCR,SAI_XCR_CSR_MASK,r->rxcr_before);
  if(!r->rx_restore_rc)r->rx_restore_rc=rd(p,SAI_RXCR,&r->rxcr_restored);
  if(!r->rx_restore_rc&&(r->rxcr_restored&SAI_XCR_CSR_MASK)!=(r->rxcr_before&SAI_XCR_CSR_MASK))r->rx_restore_rc=-71;
 }
 if(!r->stop_rc&&!r->restore_rc&&!r->rx_restore_rc&&!r->amp_rc)r->held=0;''',1)
t=t.replace('r->restore_rc?r->restore_rc:r->amp_rc', 'r->restore_rc?r->restore_rc:(r->rx_restore_rc?r->rx_restore_rc:r->amp_rc)',1)
t=t.replace('DL_ROUTE_DEFAULT,0,r);','DL_ROUTE_DEFAULT,0,1,r);').replace('frames,route,0,r);','frames,route,0,1,r);').replace('DL_ROUTE_DEFAULT,1,r);','DL_ROUTE_DEFAULT,1,1,r);')
t+='''
int dl_run_numbered_rx2(const struct dl_port*p,int prepared,int common,uint32_t mclk,
 uint32_t*capture,unsigned capacity,struct dl_result*r)
{return run_route(p,prepared,common,mclk,capture,capacity,128,DL_ROUTE_DEFAULT,1,2,r);}
'''
h=oldh.replace('int result,stop_rc,restore_rc,amp_rc,held;', 'int result,stop_rc,restore_rc,amp_rc,held;\n int rx_restore_rc;\n uint32_t rxcr_before,rxcr_active,rxcr_restored;',1)
h=h.replace('#endif','''/* Single variable: RX CSR=2 lanes, TX remains1; numbered/default route.
 * Fixed128 received WORD PAIRS (not128 LRCK frames in this mode).
 * RX CSR restored after successful stop; rx_restore_rc failure retains held. */
int dl_run_numbered_rx2(const struct dl_port *,int,int,uint32_t,uint32_t *,unsigned,
 struct dl_result *);
#endif''')
(c/'duplex.c').write_text(t);(c/'duplex.h').write_text(h)
(p/'rx-csr2.patch').write_text(''.join(difflib.unified_diff(oldc.splitlines(True),t.splitlines(True),fromfile='a/app/k7sound/duplex.c',tofile='b/app/k7sound/duplex.c'))+''.join(difflib.unified_diff(oldh.splitlines(True),h.splitlines(True),fromfile='a/app/k7sound/duplex.h',tofile='b/app/k7sound/duplex.h')))
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'candidate/duplex.c','test.c','-Icandidate','-o','test-'+opt+'.exe']
 a=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(a.stdout);assert a.returncode==0,a.stdout
 b=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(b.stdout);assert b.returncode==0,b.stdout
 runs.append(dict(command=cmd,compile_rc=a.returncode,test_rc=b.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 RX CSR2 single-variable candidate')
