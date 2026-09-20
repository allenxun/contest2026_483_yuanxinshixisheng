#include "pio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct sim {uint32_t reg[32];unsigned fifo,maximum,words,rx,arm,on,off,writes;uint64_t now;int mode;};
static uint64_t tm(void*x){struct sim*s=x;return s->now+=5;}
static int arm(void*x){struct sim*s=x;assert((s->reg[4]&15)==3 && !s->words);s->arm++;s->now+=30000;return s->mode==1?-1:0;}
static int on(void*x){struct sim*s=x;assert(s->reg[4]&12);s->on++;return s->mode==2?-1:0;}
static int off(void*x){struct sim*s=x;s->off++;return s->mode==3?-1:0;}
static int rd(void*x,uint32_t o,uint32_t*v){struct sim*s=x;
 if(o==0x70){*v=0x23073576;return 0;}
 if(o==0x6c){*v=s->mode==4&&s->writes?0:14;return 0;}
 if(o==0x14||o==0x2c){*v=0;return 0;}
 if(o==0x1c){if((s->reg[4]&4)&&s->fifo>=2)s->fifo-=2;*v=s->fifo;return 0;}
 if(o==0x20){*v=(s->reg[4]&8)&&s->mode!=5?2:0;return 0;}
 if(o==0x34){*v=s->rx++;return 0;}
 *v=s->reg[o/4];return 0;}
static int wr(void*x,uint32_t o,uint32_t v){struct sim*s=x;s->writes++;
 if(o==0x30){assert(s->arm && s->fifo<16);s->fifo++;s->words++;
   if(s->fifo>s->maximum)s->maximum=s->fifo;
   assert(v==(1u<<27)||v==0u-(1u<<27));}
 s->reg[o/4]=v;return 0;}
int main(void){struct sim s={0};struct pio_result r;static uint32_t data[96000];
 struct pio_port p={&s,rd,wr,tm,arm,on,off,1u<<27};
 assert(!pio_run(&p,1,4096000,1,NULL,0,3200,&r));
 assert(s.words==6400&&s.maximum==16&&r.prefill_words==16&&r.max_fifo==16);
 assert(s.arm==1&&s.on==1&&s.off==1&&!r.held);
 memset(&s,0,sizeof s);assert(!pio_run(&p,1,4096000,0,data,96000,48000,&r));
 assert(s.rx==96000&&r.frames==48000&&s.on==1&&!r.held);
 memset(&s,0,sizeof s);s.mode=1;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&!s.on&&s.off==1&&!s.words);
 memset(&s,0,sizeof s);s.mode=2;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&s.off==1);
 memset(&s,0,sizeof s);s.mode=3;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&r.held);
 memset(&s,0,sizeof s);s.mode=4;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&r.held&&s.off==1);
 /* mode4 has idle=14 prewrite then stop failure */
 memset(&s,0,sizeof s);s.mode=5;assert(pio_run(&p,1,4096000,0,data,96000,3200,&r)==-110&&!r.held);
 memset(&s,0,sizeof s);assert(pio_run(&p,1,4096000,1,NULL,0,3201,&r)==-22&&!s.writes);
 assert(pio_run(&p,1,4096000,0,data,96000,48001,&r)==-22);
 puts("PASS v2: arm-before-prefill/stream, fast amp hooks, FIFO<=16,3200TX/48000RX,errors and bounds");return 0;}
