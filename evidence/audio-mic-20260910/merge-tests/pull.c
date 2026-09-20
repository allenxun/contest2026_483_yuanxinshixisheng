#include "platform.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"failed %d\n",__LINE__);exit(1);}}while(0)
struct mock{uintptr_t a[32];uint32_t v[32];unsigned n;uint64_t t;};
static unsigned idx(struct mock*m,uintptr_t a){unsigned i;for(i=0;i<m->n;i++)if(m->a[i]==a)return i;CHECK(m->n<32);m->a[m->n]=a;return m->n++;}
static int rd(void*p,uintptr_t a,uint32_t*v){struct mock*m=p;
 if(a==0x27380570){*v=0x100;return 0;}
 if(a==0x27380120||a==0x27380128){*v=0;return 0;}
 if(a==0x2a610070){*v=0x23073576;return 0;}
 *v=m->v[idx(m,a)];return 0;}
static int wr(void*p,uintptr_t a,uint32_t v){struct mock*m=p;unsigned i=idx(m,a);uint32_t mask=v>>16;
 if(a==0x27200330)m->v[i]=v;else m->v[i]=(m->v[i]&~mask)|(v&mask);return 0;}
static uint64_t us(void*p){return ++((struct mock*)p)->t;}
int main(void){struct mock m={0};struct sap_state s={0};struct sap_port p={&m,rd,wr,us};
 m.v[idx(&m,0x26046144)]=0x5555;
 CHECK(!sap_setup(&p,&s,1));CHECK(m.v[idx(&m,0x26046144)]==0x5515);CHECK(s.old[9]==0x5555);
 CHECK(sap_cleanup(&p,&s,0)==-16);CHECK(m.v[idx(&m,0x26046144)]==0x5515);
 CHECK(!sap_cleanup(&p,&s,1));CHECK(m.v[idx(&m,0x26046144)]==0x5555);
 puts("PASS actual platform10 pull-none maskc0 setup readback restore readback; neighbors preserved, synthetic only");return 0;}
