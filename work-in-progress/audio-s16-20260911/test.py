import pathlib,subprocess,json,hashlib
r=pathlib.Path('E:/openvela/VelaVision');out=r/'work-in-progress/audio-s16-20260911'
s=(r/'work-in-progress/parallel-neon-probe-medium/audio-sai1-pio-v3/test.c').read_text()
s=s.replace('uint64_t now;', 'uint64_t now,last_rx,pause_gap;')
s=s.replace('return s->now+=5;', 'if(s->mode==8 && s->rx==16)return s->now;return s->now+=5;')
s=s.replace('if(o==0x14||o==0x2c)', 'if(o==0x2c && s->mode==7 && s->rx==16 && s->now-s->last_rx>100){*v=131072;return 0;}\n if(o==0x14||o==0x2c)')
s=s.replace('*v=s->rx++;return 0;', 'if(s->rx==16)s->pause_gap=s->now-s->last_rx;s->last_rx=s->now;*v=s->rx++;return 0;')
s=s.replace(' puts("PASS v3:', ''' memset(&s,0,sizeof s);assert(!pio_run_pause250(&p,1,4096000,data,96000,&r));
 assert(r.frames==128 && s.rx==256 && !r.held && r.pause_end_us-r.pause_start_us>=250 && s.pause_gap>=250);
 memset(&s,0,sizeof s);s.mode=7;assert(pio_run_pause250(&p,1,4096000,data,96000,&r)==-75 && s.rx==16 && !r.held);
 memset(&s,0,sizeof s);s.mode=8;assert(pio_run_pause250(&p,1,4096000,data,96000,&r)==-110 && s.rx==16 && !r.held);
 puts("PASS pause normal/overflow/frozen-clock; v3:''')
s=s.replace(' puts("PASS pause normal/overflow/frozen-clock; v3:', ''' memset(&s,0,sizeof s);s.reg[0x38/4]=0xe4e4;assert(!pio_run_rx4(&p,1,4096000,data,96000,128,&r));
 assert(s.reg[8/4]==0x00700fff && s.reg[0x38/4]==0xe4e4);
 memset(&s,0,sizeof s);s.reg[0x38/4]=0xe4e4;assert(!pio_run_rx4_all(&p,1,4096000,data,96000,128,&r));
 assert(s.reg[8/4]==0x00700fff && s.reg[0x38/4]==0x00e4);
 memset(&s,0,sizeof s);assert(!pio_run_rde(&p,1,4096000,data,96000,128,&r));
 assert(s.rx==256 && r.frames==128 && r.rx_trace.init[4]==0x010f0000 && !r.dma_restore_result && s.reg[0x24/4]==0);
 memset(&s,0,sizeof s);assert(!pio_run16(&p,1,4096000,data,96000,128,&r));
 assert(s.rx==256 && r.frames==128 && s.reg[8/4]==0x00400def && s.reg[4/4]==0x0100f01f && s.reg[0x18/4]==0x38);
 assert(pio_run16(&p,1,4096001,data,96000,128,&r)==-22);
 memset(&s,0,sizeof s);s.reg[0x0c/4]=0x104;assert(!pio_run_mono(&p,1,4096000,data,96000,128,&r));
 assert(s.rx==128 && r.frames==128 && !r.mono_restore_result && s.reg[0x0c/4]==0x104);
 for(int i=0;i<128;i++)assert(data[2*i]==data[2*i+1]);
 puts("PASS mono slot0/read-one/duplicate/restore; RX4 routes; RDE gate/restore; S16 recipe; pause normal/overflow/frozen-clock; v3:''')
(out/'test.c').write_text(s)
rows=[]
for opt in ['O0','O2']:
 exe=out/(opt+'.exe');cmd=['D:/software/mingw64/mingw64/bin/gcc.exe','-'+opt,'-Wall','-Wextra','-Werror','-I'+str(r/'app/k7sound'),str(out/'test.c'),str(r/'app/k7sound/pio.c'),'-o',str(exe)]
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(out/(opt+'-build.log')).write_bytes(p.stdout);assert p.returncode==0,p.stdout.decode()
 p=subprocess.run([str(exe)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20);(out/(opt+'-test.log')).write_bytes(p.stdout);assert p.returncode==0,p.stdout.decode();rows.append({'opt':opt,'exit_code':p.returncode})
(out/'host-result.json').write_text(json.dumps({'runs':rows,'sources':{str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [r/'app/k7sound/pio.c',r/'app/k7sound/pio.h',out/'test.c']}},indent=2));print(rows)



