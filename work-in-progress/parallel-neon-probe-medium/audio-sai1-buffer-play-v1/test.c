#include "pio.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct sim {uint32_t reg[32];unsigned fifo,maximum,words,rx,arm,on,off,writes;uint64_t now;int mode;const uint32_t *source;unsigned limit;};
static uint64_t tm(void*x){struct sim*s=x;return s->now+=5;}
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
 if(o==0x14||o==0x2c){*v=0;return 0;}
 if(o==0x1c){if((s->reg[4]&4)&&s->fifo>=2)s->fifo-=2;*v=encode(s->fifo);
   if(s->mode==6&&s->words)*v=4;
   return 0;}
 if(o==0x20){*v=(s->reg[4]&8)&&s->mode!=5?encode(2):0;return 0;}
 if(o==0x34){*v=s->rx++;return 0;}
 *v=s->reg[o/4];return 0;}
static int wr(void*x,uint32_t o,uint32_t v){struct sim*s=x;s->writes++;
 if(o==0x30){assert(s->arm && s->fifo<16);s->fifo++;s->words++;
   if(s->fifo>s->maximum)s->maximum=s->fifo;
   if(s->source){assert(s->words<=s->limit);assert(v==s->source[s->words-1]);}
   else assert(v==(1u<<27)||v==0u-(1u<<27));}
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
 {
  unsigned i,j;const unsigned lengths[]={1,7,8,9,3200,48000};
  for(i=0;i<96000;i++)data[i]=0x9e3779b9u*i+0x80000000u;
  for(j=0;j<sizeof lengths/sizeof lengths[0];j++){
   unsigned n=lengths[j];memset(&s,0,sizeof s);s.source=data;s.limit=2*n;
   assert(!pio_play_buffer(&p,1,4096000,data,96000,n,&r));
   assert(s.words==2*n&&r.frames==n&&s.maximum<=16&&!r.held);
   assert(r.prefill_words==(n<8?2*n:16));
  }
  for(i=0;i<96000;i++)assert(data[i]==0x9e3779b9u*i+0x80000000u);
  memset(&s,0,sizeof s);
  assert(pio_play_buffer(&p,1,4096000,NULL,96000,1,&r)==-22);
  assert(pio_play_buffer(&p,1,4096000,data,1,1,&r)==-22);
  assert(pio_play_buffer(&p,1,4096000,data,95999,48000,&r)==-22);
  assert(pio_play_buffer(&p,1,4096000,data,96000,0,&r)==-22);
  assert(pio_play_buffer(&p,1,4096000,data,96000,48001,&r)==-22);
  assert(pio_play_buffer(&p,1,4096000,data,~0u,~0u,&r)==-22&&!s.writes);
 }
 puts("PASS buffer: exact stereo words1/7/8/9/3200/48000frames,immutable input,bounds,all v3 regression");return 0;}
