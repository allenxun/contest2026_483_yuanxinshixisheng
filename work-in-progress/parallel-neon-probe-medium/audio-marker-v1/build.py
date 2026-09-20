import pathlib,hashlib,json,difflib,subprocess
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['app/k7sound/duplex.c','app/k7sound/duplex.h','app/k7sound/input/rockchip_sai.h',
 'evidence/audio-route-20260910/k7sound-loopback-rxall-20260910-213805.bin',
 'evidence/audio-route-20260910/k7sound-loopback-20260910-213816.bin']
manifest=[]
for n in names:
 b=(root/n).read_bytes();f=p/'input'/n;f.parent.mkdir(parents=True,exist_ok=True)
 if f.exists():assert f.read_bytes()==b,'Frozen input changed'
 else:f.write_bytes(b)
 manifest.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(manifest,indent=2))
c=p/'candidate';(c/'input').mkdir(parents=True,exist_ok=True)
(c/'input/rockchip_sai.h').write_bytes((p/'input'/names[2]).read_bytes())
oldc=(p/'input'/names[0]).read_text();oldh=(p/'input'/names[1]).read_text()
text=oldc.replace('static uint32_t marker(unsigned n)', '''int dl_numbered_marker(unsigned n,uint32_t*out)
{
 if(!out||n>=288u)return -22;
 *out=0x01000000u|((n&7u)<<20)|(((n>>3)+1u)<<8);
 return 0;
}
static uint32_t marker(unsigned n,int numbered)''',1)
text=text.replace('0x0505ab00,0x0606cd00,0x0707ef00,0x08081100};return a[n&7];}',
 '0x0505ab00,0x0606cd00,0x0707ef00,0x08081100};\n /* Numbered mode is fixed128 frames; enqueue cap enforces n<288. */\n if(numbered)return 0x01000000u|((n&7u)<<20)|(((n>>3)+1u)<<8);\n return a[n&7];}',1)
text=text.replace('unsigned frames,int route,struct dl_result*r)\n{','unsigned frames,int route,int numbered,struct dl_result*r)\n{',1)
text=text.replace('memset(r,0,sizeof(*r));','memset(r,0,sizeof(*r));\n if(numbered&&(frames!=128||route!=DL_ROUTE_DEFAULT))return r->result=-22;',1)
text=text.replace('if(r->path_before&0x30000)return r->result=-38;',
 'if(r->path_before&0x30000)return r->result=-38;\n /* Numbered experiment requires the same default RX route as baseline. */\n if(numbered&&(r->path_before&0xff00u)!=0xe400u)return r->result=-38;',1)
text=text.replace('marker(r->tx_words)','marker(r->tx_words,numbered)')
text=text.replace('frames,DL_ROUTE_DEFAULT,r);','frames,DL_ROUTE_DEFAULT,0,r);')
text=text.replace('frames,route,r);','frames,route,0,r);')
text+='''
int dl_run_numbered(const struct dl_port*p,int prepared,int common,uint32_t mclk,
 uint32_t*capture,unsigned capacity,struct dl_result*r)
{return run_route(p,prepared,common,mclk,capture,capacity,128,DL_ROUTE_DEFAULT,1,r);}
'''
h=oldh.replace('#endif','''/* Explicit 128-frame numbered source; RX route must be default e4xx.
 * Cannot combine with RX_ALL. n is enqueue WORD index, not FIFO bank/frame. */
int dl_numbered_marker(unsigned n,uint32_t *out); /* 0<=n<288, else -22 */
int dl_run_numbered(const struct dl_port *,int,int,uint32_t,uint32_t *,unsigned,
 struct dl_result *);
#endif''')
(c/'duplex.c').write_text(text);(c/'duplex.h').write_text(h)
diff=''.join(difflib.unified_diff(oldc.splitlines(True),text.splitlines(True),fromfile='a/app/k7sound/duplex.c',tofile='b/app/k7sound/duplex.c'))
diff+=''.join(difflib.unified_diff(oldh.splitlines(True),h.splitlines(True),fromfile='a/app/k7sound/duplex.h',tofile='b/app/k7sound/duplex.h'))
(p/'numbered-marker.patch').write_text(diff)
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'candidate/duplex.c','test.c','-Icandidate','-o','test-'+opt+'.exe']
 a=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(a.stdout);assert a.returncode==0,a.stdout
 b=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(b.stdout);assert b.returncode==0,b.stdout
 runs.append(dict(command=cmd,compile_rc=a.returncode,test_rc=b.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 default preserved and numbered 128-frame source')
