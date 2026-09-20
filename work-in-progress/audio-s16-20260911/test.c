#include "pio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct sim {uint32_t reg[32];unsigned fifo,maximum,words,rx,arm,on,off,writes;uint64_t now,last_rx,pause_gap;int mode;};
static uint64_t tm(void*x){struct sim*s=x;if(s->mode==8 && s->rx==16)return s->now;return s->now+=5;}
/* Model storage distributed across4 FIFO fields; this is a hypothesis used
 * to test the vendor aggregation, not a claim about the physical mapping. */
static uint32_t encode(unsigned total){uint32_t v=0;unsigned i;
 for(i=0;i<4;i++){v|=(total/4+(i<total%4))<<(6*i);}return v;}
static int arm(void*x){struct sim*s=x;assert((s->reg[4]&15)==3 && !s->words);s->arm++;s->now+=30000;return s->mode==1?-1:0;}
static int on(void*x){struct sim*s=x;assert(s->reg[4]&12);s->on++;return s->mode==2?-1:0;}
static int off(void*x){struct sim*s=x;s->off++;return s->mode==3?-1:0;}
static int rd(void*x,uint32_t o,uint32_t*v){struct sim*s=x;
 if(o==0x70){*v=0x23073576;return 0;}
 if(o==0x6c){*v=s->mode==4&&s->writes?0:14;return 0;}
 if(o==0x2c && s->mode==7 && s->rx==16 && s->now-s->last_rx>100){*v=131072;return 0;}
 if(o==0x14||o==0x2c){*v=0;return 0;}
 if(o==0x1c){if((s->reg[4]&4)&&s->fifo>=2)s->fifo-=2;*v=encode(s->fifo);
   if(s->mode==6&&s->words)*v=4;
   return 0;}
 if(o==0x20){*v=(s->reg[4]&8)&&s->mode!=5?encode(2):0;return 0;}
 if(o==0x34){if(s->rx==16)s->pause_gap=s->now-s->last_rx;s->last_rx=s->now;*v=s->rx++;return 0;}
 *v=s->reg[o/4];return 0;}
static int wr(void*x,uint32_t o,uint32_t v){struct sim*s=x;s->writes++;
 if(o==0x30){assert(s->arm && s->fifo<16);s->fifo++;s->words++;
   if(s->fifo>s->maximum)s->maximum=s->fifo;
   assert(v==(1u<<27)||v==0u-(1u<<27));}
 s->reg[o/4]=v;return 0;}
int main(void){struct sim s={0};struct pio_result r;static uint32_t data[96000];
 struct pio_port p={&s,rd,wr,tm,arm,on,off,1u<<27};
 assert(pio_fifo_count(0x104104)==16 && pio_fifo_count(0x41)==2);
 assert(pio_fifo_count(0xffffff)==252 && pio_fifo_count(0xff000000)==0);
 assert(pio_fifo_count(16)==16 && pio_fifo_count(4)==4);
 assert(!pio_run(&p,1,4096000,1,NULL,0,3200,&r));
 assert(s.words==6400&&s.maximum==16&&r.prefill_words==16&&r.max_fifo==16);
 assert(r.first_fifo_raw==0x104104 && r.last_fifo_raw==0);
 assert(s.arm==1&&s.on==1&&s.off==1&&!r.held);
 memset(&s,0,sizeof s);assert(!pio_run(&p,1,4096000,0,data,96000,48000,&r));
 assert(s.rx==96000&&r.frames==48000&&s.on==1&&!r.held);
 assert(r.first_fifo_raw==0x41 && r.last_fifo_raw==0x41);
 memset(&s,0,sizeof s);s.mode=1;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&!s.on&&s.off==1&&!s.words);
 memset(&s,0,sizeof s);s.mode=2;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&s.off==1);
 memset(&s,0,sizeof s);s.mode=3;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&r.held);
 memset(&s,0,sizeof s);s.mode=4;assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)<0&&r.held&&s.off==1);
 /* mode4 has idle=14 prewrite then stop failure */
 memset(&s,0,sizeof s);s.mode=5;assert(pio_run(&p,1,4096000,0,data,96000,3200,&r)==-110&&!r.held);
 memset(&s,0,sizeof s);assert(pio_run(&p,1,4096000,1,NULL,0,3201,&r)==-22&&!s.writes);
 assert(pio_run(&p,1,4096000,0,data,96000,48001,&r)==-22);
 memset(&s,0,sizeof s);s.mode=6;
 assert(pio_run(&p,1,4096000,1,NULL,0,3200,&r)==-71);
 assert(s.words==16 && !s.on && r.first_fifo_raw==4 && r.max_fifo==4 && !r.held);
 memset(&s,0,sizeof s);assert(!pio_run_pause250(&p,1,4096000,data,96000,&r));
 assert(r.frames==128 && s.rx==256 && !r.held && r.pause_end_us-r.pause_start_us>=250 && s.pause_gap>=250);
 memset(&s,0,sizeof s);s.mode=7;assert(pio_run_pause250(&p,1,4096000,data,96000,&r)==-75 && s.rx==16 && !r.held);
 memset(&s,0,sizeof s);s.mode=8;assert(pio_run_pause250(&p,1,4096000,data,96000,&r)==-110 && s.rx==16 && !r.held);
 memset(&s,0,sizeof s);s.reg[0x38/4]=0xe4e4;assert(!pio_run_rx4(&p,1,4096000,data,96000,128,&r));
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
 puts("PASS mono slot0/read-one/duplicate/restore; RX4 routes; RDE gate/restore; S16 recipe; pause normal/overflow/frozen-clock; v3: vendor sum4 FIFO, strict16word prefill, raw diagnostics,3200TX/48000RX and v2 bounds");return 0;}
