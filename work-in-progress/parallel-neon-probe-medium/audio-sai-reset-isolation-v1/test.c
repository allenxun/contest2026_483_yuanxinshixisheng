#include "reset_probe.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct mock{uint64_t t;int reset[2],calls,busy,stalled,fail;};
static int read_sai(void*x,uint32_t a,uint32_t*v){struct mock*m=x;
 assert(!m->reset[0]&&!m->reset[1]);*v=0;
 if(a==0x70)*v=0x23073576;
 if(a==0x6c)*v=14;
 if(a==0x10&&m->busy)*v=8;
 return 0;}
static int set(void*x,enum sr_domain d,int a){struct mock*m=x;
 assert((int)d==m->calls/2&&a==!(m->calls&1));m->calls++;
 if(m->fail&&m->calls==m->fail)return -1;
 m->reset[d]=a;return 0;}
static int get(void*x,enum sr_domain d,int*a){struct mock*m=x;*a=m->reset[d];return 0;}
static uint64_t now(void*x){struct mock*m=x;if(!m->stalled)m->t++;return m->t;}
int main(void){struct mock m={0};struct sr_result r={0};struct sr_port p={&m,read_sai,set,get,now};
 assert(sr_once(&p,&r,0)==-38&&!m.calls);
 assert(!sr_once(&p,&r,1)&&m.calls==4&&r.completed&&r.needs_reapply&&!r.held&&m.t>=40);
 assert(sr_once(&p,&r,1)==-16);
 memset(&r,0,sizeof r);memset(&m,0,sizeof m);m.busy=1;
 assert(sr_once(&p,&r,1)==-16&&!m.calls);
 memset(&r,0,sizeof r);memset(&m,0,sizeof m);m.stalled=1;
 assert(sr_once(&p,&r,1)==-110&&r.held&&m.calls==1);
 memset(&r,0,sizeof r);memset(&m,0,sizeof m);m.fail=2;
 assert(sr_once(&p,&r,1)==-5&&r.held&&!r.completed);
 puts("PASS controlled reset: H+/H-/M+/M- delays, active reject, fail-held, no access while asserted");return 0;}
