#include <stdio.h>
#include <stdlib.h>
#include "pio.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"fail %d\n",__LINE__);exit(1);}}while(0)
struct mock {uint32_t regs[32];uint64_t t,div_at,enabled_at;unsigned words;int mode;};
static uint64_t tick(void*p){struct mock*m=p;if(m->mode==1)return 0;if(m->mode==2&&m->t==7)return 3;return ++m->t;}
static int readreg(void*p,uint32_t o,uint32_t*v){struct mock*m=p;*v=m->regs[o/4];
 if(o==SAI_VERSION)*v=SAI_VER_2307;
 if(o==SAI_STATUS)*v=14;
 if(o==SAI_CLR)*v=0;
 if(o==SAI_RXFIFOLR)*v=(m->regs[SAI_XFER/4]&8)?2:0;
 if(o==SAI_RXDR)*v=0x12340000u+m->words++;
 return 0;}
static int writereg(void*p,uint32_t o,uint32_t v){struct mock*m=p;m->regs[o/4]=v;if(o==SAI_CKR)m->div_at=m->t;
 if(o==SAI_XFER&&(v&3)==3&&!m->enabled_at)m->enabled_at=m->t;
 return 0;}
static int hook(void*p){(void)p;return 0;}
int main(void){struct mock m={0};struct pio_port p={&m,readreg,writereg,tick,hook,hook,hook,1};struct pio_result out;uint32_t data[2];
 CHECK(!clockwait20(&p)&&m.t==21);
 m=(struct mock){0};m.mode=1;CHECK(clockwait20(&p)==-110);
 m=(struct mock){0};m.mode=2;CHECK(clockwait20(&p)==-5);
 m=(struct mock){0};CHECK(!pio_run_clockwait(&p,1,4096000,0,data,2,1,&out));CHECK(m.enabled_at-m.div_at>=20);CHECK(out.frames==1&&m.words==2&&data[0]==0x12340000&&data[1]==0x12340001);
 printf("opt-in wait=%llu us frames=%u words=%u\n",(unsigned long long)(m.enabled_at-m.div_at),out.frames,m.words);
 m=(struct mock){0};CHECK(!pio_run(&p,1,4096000,0,data,2,1,&out));CHECK(m.enabled_at-m.div_at<20&&out.frames==1&&m.words==2);
 m=(struct mock){0};m.mode=1;CHECK(pio_run_clockwait(&p,1,4096000,0,data,2,1,&out)==-110&&!m.enabled_at&&!m.words);
 puts("PASS 20us/stalled/backward/opt-in/legacy/FIFO identical; synthetic actual candidate C");return 0;}
