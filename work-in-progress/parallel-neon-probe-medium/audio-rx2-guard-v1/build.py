import pathlib,hashlib,json,difflib,subprocess
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['app/k7sound/duplex.c','app/k7sound/duplex.h','app/k7sound/input/rockchip_sai.h',
 'work-in-progress/parallel-neon-probe-medium/audio-rx2-analysis-v1/rx2_ready.c']
items=[]
for n in names:
 b=(root/n).read_bytes();f=p/'input'/n;f.parent.mkdir(parents=True,exist_ok=True)
 if f.exists():assert f.read_bytes()==b
 else:f.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
c=p/'candidate';(c/'input').mkdir(parents=True,exist_ok=True)
(c/'input/rockchip_sai.h').write_bytes((p/'input'/names[2]).read_bytes())
(c/'rx2_ready.c').write_bytes((p/'input'/names[3]).read_bytes())
old=(p/'input'/names[0]).read_text();oldh=(p/'input'/names[1]).read_text()
t=old.replace('#include <stddef.h>','#include <stddef.h>\nint rx2_pair_ready(uint32_t raw);',1)
t=t.replace('unsigned rx_lanes,struct dl_result*r)','unsigned rx_lanes,int guarded,struct dl_result*r)',1)
t=t.replace('int rc=-5,clocks_attempted=0,path_saved=0,rx_saved=0;', 'int rc=-5,clocks_attempted=0,path_saved=0,rx_saved=0,ready=0;',1)
t=t.replace('memset(r,0,sizeof(*r));','memset(r,0,sizeof(*r));\n if(guarded&&rx_lanes!=2)return r->result=-22;',1)
t=t.replace('t=count(t);v=count(v);','ready=guarded?rx2_pair_ready(v):(count(v)>=2);\n  if(ready<0){rc=-71;goto done;}\n  t=count(t);v=count(v);',1)
t=t.replace('if(v>=2){for(i=0;i<2;i++)','if(ready){for(i=0;i<2;i++)',1)
t=t.replace(',0,1,r);',',0,1,0,r);').replace(',1,1,r);',',1,1,0,r);').replace(',1,2,r);',',1,2,0,r);')
t+='''
int dl_run_numbered_rx2_guard(const struct dl_port*p,int prepared,int common,uint32_t mclk,
 uint32_t*capture,unsigned capacity,struct dl_result*r)
{return run_route(p,prepared,common,mclk,capture,capacity,128,DL_ROUTE_DEFAULT,1,2,1,r);}
'''
h=oldh.replace('#endif','''/* Explicit guarded RX2: both observed banks0/1 must have>=2 entries;
 * unexpected banks/depth reject. Other entry points keep original readiness. */
int dl_run_numbered_rx2_guard(const struct dl_port *,int,int,uint32_t,uint32_t *,unsigned,
 struct dl_result *);
#endif''')
(c/'duplex.c').write_text(t);(c/'duplex.h').write_text(h)
(p/'rx2-guard.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),t.splitlines(True),fromfile='a/app/k7sound/duplex.c',tofile='b/app/k7sound/duplex.c'))+''.join(difflib.unified_diff(oldh.splitlines(True),h.splitlines(True),fromfile='a/app/k7sound/duplex.h',tofile='b/app/k7sound/duplex.h')))
with (p/'rx2-guard.patch').open('a') as f:
 f.write(''.join(difflib.unified_diff([], (c/'rx2_ready.c').read_text().splitlines(True),fromfile='/dev/null',tofile='b/app/k7sound/rx2_ready.c')))
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'candidate/duplex.c','candidate/rx2_ready.c','test.c','-Icandidate','-o','test-'+opt+'.exe']
 a=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(a.stdout);assert a.returncode==0,a.stdout
 b=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(b.stdout);assert b.returncode==0,b.stdout
 runs.append(dict(command=cmd,compile_rc=a.returncode,test_rc=b.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS guarded RX2 O0/O2 and legacy regression')
