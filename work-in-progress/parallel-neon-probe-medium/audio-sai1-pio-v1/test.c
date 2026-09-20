#include "pio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct sim {uint32_t reg[32];unsigned writes,txwords,rxwords;uint64_t now;int mode;};
static uint64_t tm(void *x){struct sim*s=x;if(s->mode!=5)s->now+=25;return s->now;}
static int readreg(void*x,uint32_t o,uint32_t*v){
 struct sim*s=x;
 if(o==0x6c){*v=s->mode==4 && s->writes?0:14;return 0;}
 if(o==0x14){*v=0;return 0;}
 if(o==0x2c){*v=s->mode==3? (1u<<17):0;return 0;}
 if(o==0x20){*v=(s->reg[4]&8) && s->mode!=2?2:0;return 0;}
 if(o==0x1c){*v=0;return 0;}
 if(o==0x34){*v=0x12340000u+s->rxwords++;return 0;}
 *v=s->reg[o/4];return 0;
}
static int writereg(void*x,uint32_t o,uint32_t v){struct sim*s=x;s->writes++;
 if(s->mode==6)return -1;
 if(o==0x30){assert(v==(1u<<20)||v==0u-(1u<<20));s->txwords++;}
 s->reg[o/4]=v;return 0;}
static void init(struct sim*s){memset(s,0,sizeof *s);s->reg[0x70/4]=0x23073576;}
int main(void){
 struct sim s;struct pio_result r;uint32_t data[6400];
 struct pio_stats st;
 struct pio_port p={&s,readreg,writereg,tm};
 init(&s);assert(pio_run(&p,0,12288000,0,data,6400,&r)==-38 && !s.writes);
 init(&s);s.reg[0x70/4]=0x23112118;
 assert(pio_run(&p,1,12288000,0,data,6400,&r)==-38 && !s.writes);
 init(&s);assert(pio_run(&p,1,12288001,0,data,6400,&r)==-22 && !s.writes);
 init(&s);s.reg[4]=8;assert(pio_run(&p,1,12288000,0,data,6400,&r)==-16 && !s.writes);
 init(&s);assert(pio_run(&p,1,12288000,0,data,6399,&r)==-22 && !s.writes);
 init(&s);assert(!pio_run(&p,1,12288000,0,data,6400,&r));
 assert(r.frames==3200 && !r.held && s.rxwords==6400 && data[6399]==0x123418ff);
 assert(s.reg[0x18/4]==88 && s.reg[0x04/4]==0x0101f03f);
 init(&s);assert(!pio_run(&p,1,4096000,1,NULL,0,&r));
 assert(s.txwords==6400 && r.frames==3200 && !r.held);
 init(&s);s.mode=2;assert(pio_run(&p,1,12288000,0,data,6400,&r)==-110 && !r.held);
 init(&s);s.mode=3;assert(pio_run(&p,1,12288000,0,data,6400,&r)==-75 && !r.held);
 init(&s);s.mode=4;assert(pio_run(&p,1,12288000,0,data,6400,&r)==-110 && r.held);
 init(&s);s.mode=5;/* stalled clock still finite loop count */
 s.mode=5;assert(!pio_run(&p,1,12288000,0,data,6400,&r));
 init(&s);s.mode=6;assert(pio_run(&p,1,12288000,0,data,6400,&r)==-5 && r.held);
 data[0]=0x80000000;data[1]=0x7fffffff;data[2]=0;data[3]=0xffffffff;
 assert(!pio_summarize(data,2,&st));
 assert(st.min[0]==INT32_MIN && st.sum[1]==2147483646 && st.nonzero[0]==1);
 assert(pio_summarize(data,3201,&st)==-22);
 puts("PASS simulated raw32 capture/tone, version/preconditions, deadline/xrun/stop/MMIO failure");
 return 0;
}
