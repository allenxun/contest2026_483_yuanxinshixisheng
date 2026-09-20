#include "observe.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed %d\n",__LINE__);exit(1);}}while(0)
struct mock{uint64_t t;unsigned n;int mode;};
static uint64_t ticks(void*p){struct mock*m=p;if(m->mode==1)return 0;if(m->mode==2&&m->t>4)return 1;return ++m->t;}
static uint32_t ext(void*p){struct mock*m=p;return (m->n++&1)?0x2c:0;}
int main(void){struct mock m={0};struct apo_port p={&m,ticks,ext,1000};struct apo_result r;
 CHECK(!apo_observe(&p,&r)&&r.complete&&r.samples==19&&r.changes[0]==18&&!r.high[3]);
 printf("synthetic complete samples=%u changes=%u,%u,%u,%u elapsed=%llu\n",r.samples,r.changes[0],r.changes[1],r.changes[2],r.changes[3],(unsigned long long)r.elapsed_ticks);
 m=(struct mock){0};m.mode=1;CHECK(apo_observe(&p,&r)==-ETIMEDOUT&&r.samples==1000000&&!r.complete);
 m=(struct mock){0};m.mode=2;CHECK(apo_observe(&p,&r)==-EIO&&!r.complete);
 p.frequency=0;CHECK(apo_observe(&p,&r)==-EINVAL);
 puts("PASS fixed-window/count-bound/backward-clock/invalid-frequency; synthetic only");return 0;}
