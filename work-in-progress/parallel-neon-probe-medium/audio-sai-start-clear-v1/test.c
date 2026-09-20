#include "start_clear.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct mock{unsigned writes,polls;uint64_t t;int busy,dma,stuck,residue,fail,clock_stuck;};
static int rd(void*x,uint32_t a,uint32_t*v){struct mock*m=x;*v=0;
 if(a==0x70)*v=0x23073576;
 if(a==0x10&&m->busy)*v=8;
 if(a==0x24&&m->dma)*v=0x1000000;
 if(a==0x6c)*v=14;
 if(a==0x14&&m->writes){m->polls++;*v=m->stuck||m->polls<3?3:0;}
 if(a==0x1c||a==0x20)*v=!m->writes||m->residue?0x104104:0;
 return 0;}
static int wr(void*x,uint32_t a,uint32_t v){struct mock*m=x;assert(a==0x14&&v==3);m->writes++;return m->fail?-1:0;}
static uint64_t tm(void*x){struct mock*m=x;if(!m->clock_stuck)m->t+=5;return m->t;}
int main(void){struct mock m={0};struct sc_result r={0};struct sc_port p={&m,rd,wr,tm};
 assert(sc_once(&p,&r,0)==-38&&!m.writes);
 assert(!sc_once(&p,&r,1)&&r.completed&&!r.held&&r.needs_reapply&&m.writes==1);
 assert(r.fifo_before[0]==0x104104&&!r.fifo_after[1]&&m.polls==3);
 assert(sc_once(&p,&r,1)==-16);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.busy=1;assert(sc_once(&p,&r,1)==-16&&!m.writes);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.dma=1;assert(sc_once(&p,&r,1)==-16&&!m.writes);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.stuck=1;assert(sc_once(&p,&r,1)==-110&&r.held);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.stuck=m.clock_stuck=1;assert(sc_once(&p,&r,1)==-110&&r.polls==100000);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.residue=1;assert(sc_once(&p,&r,1)==-71&&r.held);
 memset(&m,0,sizeof m);memset(&r,0,sizeof r);m.fail=1;assert(sc_once(&p,&r,1)==-5&&r.held);
 puts("PASS start-clear: onlyCLR3 write,self-clear/residue checks,active+DMA reject,timeout/stalledclock/failure held");return 0;}
