#include "platform.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct sim{uintptr_t a[32];uint32_t v[32];unsigned n,w,sai;uint64_t t;int timeout;};
static unsigned idx(struct sim*s,uintptr_t a){unsigned i;for(i=0;i<s->n;i++)if(s->a[i]==a)return i;
 assert(s->n<32);s->a[s->n]=a;return s->n++;}
static uint64_t time_us(void*x){struct sim*s=x;return s->t+=10;}
static int readreg(void*x,uintptr_t a,uint32_t*v){struct sim*s=x;
 if(a==0x27380570){*v=s->timeout?0:256;return 0;}
 if(a==0x2a610070){assert(s->w>10 && !s->timeout);s->sai++;*v=0x23073576;return 0;}
 *v=s->v[idx(s,a)];return 0;}
static int writereg(void*x,uintptr_t a,uint32_t v){struct sim*s=x;unsigned i=idx(s,a);s->w++;
 assert(a<0x2a610000||a>=0x2a611000); /* setup never writes SAI */
 if(a==0x27200330)s->v[i]=v;
 else{s->v[i]=(s->v[i]&~(v>>16))|(v&(v>>16));}return 0;}
int main(void){struct sim sim={0};struct sap_state s={0};struct sap_port p={&sim,readreg,writereg,time_us};
 assert(sap_setup(&p,&s,0)==-38&&!sim.w);
 assert(!sap_setup(&p,&s,1)&&s.ready&&s.version==0x23073576&&sim.sai==1);
 assert(s.fraction==0x00400177&&s.clk46==0x100);
 assert(sap_cleanup(&p,&s,0)==-16&&s.held);
 assert(!sap_cleanup(&p,&s,1)&&!s.held&&!s.ready);
 assert(sap_setup(&p,&s,1)==-16);
 memset(&s,0,sizeof s);memset(&sim,0,sizeof sim);sim.timeout=1;
 assert(sap_setup(&p,&s,1)==-110&&sim.sai==0&&s.held);
 assert(sap_cleanup(&p,&s,1)==-16);
 puts("PASS platform: setup clock/pins, no SAI writes, power-timeout no SAI read, cleanup gate+restore");return 0;}
