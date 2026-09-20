import pathlib,hashlib,json,difflib,subprocess
p=pathlib.Path(__file__).resolve().parent
c=p/'candidate';c.mkdir(exist_ok=True)
source=p/'input/app/k7sound'
oldc=(source/'duplex.c').read_text()
oldh=(source/'duplex.h').read_text()
text=oldc.replace('int dl_run(const struct dl_port*p,int prepared,int common,uint32_t mclk,',
 'static int run_route(const struct dl_port*p,int prepared,int common,uint32_t mclk,',1)
text=text.replace('uint32_t*capture,unsigned capacity,unsigned frames,struct dl_result*r)',
 'uint32_t*capture,unsigned capacity,unsigned frames,int route,struct dl_result*r)',1)
text=text.replace('uint32_t v,t,x,mask,value;unsigned i;',
 'uint32_t v,t,x,mask,value,pathmask;unsigned i;',1)
text=text.replace('memset(r,0,sizeof(*r));','memset(r,0,sizeof(*r));\n if(route!=DL_ROUTE_DEFAULT&&route!=DL_ROUTE_RX_ALL_SDI0)return r->result=-22;\n if(route==DL_ROUTE_RX_ALL_SDI0&&frames!=128)return r->result=-22;\n pathmask=route==DL_ROUTE_RX_ALL_SDI0?0x00fcff03u:0x00fc0303u;',1)
text=text.replace('0xfc0303u','pathmask').replace('0xfc0303','pathmask')
text+='''
int dl_run(const struct dl_port*p,int prepared,int common,uint32_t mclk,
 uint32_t*capture,unsigned capacity,unsigned frames,struct dl_result*r)
{return run_route(p,prepared,common,mclk,capture,capacity,frames,DL_ROUTE_DEFAULT,r);}
int dl_run_route(const struct dl_port*p,int prepared,int common,uint32_t mclk,
 uint32_t*capture,unsigned capacity,unsigned frames,int route,struct dl_result*r)
{return run_route(p,prepared,common,mclk,capture,capacity,frames,route,r);}
'''
h=oldh.replace('#endif','''/* Only explicit RX_ALL mode changes PATH[15:8] to select SDI0 for all
 * RX paths. Requires frames=128. All original stop/amp/fault fences remain.
 * Default dl_run remains source compatible and preserves RX paths1..3. */
enum {DL_ROUTE_DEFAULT=0,DL_ROUTE_RX_ALL_SDI0=1};
int dl_run_route(const struct dl_port *,int,int,uint32_t,uint32_t *,unsigned,
 unsigned frames,int route,struct dl_result *);
#endif''')
(c/'duplex.c').write_text(text)
(c/'duplex.h').write_text(h)
hdr=p/'input/work-in-progress/parallel-k7-audio/sources/kernel-6.1/sound/soc/rockchip/rockchip_sai.h'
(c/'input').mkdir(exist_ok=True)
(c/'input/rockchip_sai.h').write_bytes(hdr.read_bytes())
diff=''.join(difflib.unified_diff(oldc.splitlines(True),text.splitlines(True),fromfile='a/app/k7sound/duplex.c',tofile='b/app/k7sound/duplex.c'))
diff+=''.join(difflib.unified_diff(oldh.splitlines(True),h.splitlines(True),fromfile='a/app/k7sound/duplex.h',tofile='b/app/k7sound/duplex.h'))
(p/'rx-all-route.patch').write_text(diff)
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'candidate/duplex.c','test_route.c','-Icandidate','-o','test-'+opt+'.exe']
 a=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(a.stdout);assert a.returncode==0,a.stdout
 b=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(b.stdout);assert b.returncode==0,b.stdout
 runs.append(dict(command=cmd,compile_rc=a.returncode,test_rc=b.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 default and explicit RX all-SDI0 routes, restore/readback/fail fences')
