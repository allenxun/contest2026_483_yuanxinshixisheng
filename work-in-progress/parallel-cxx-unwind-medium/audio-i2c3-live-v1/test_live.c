#include "live.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct mock {uint32_t r[0x22c/4];unsigned n,locks,unlocks;uint64_t now;int fault;bool low,frozen;};
static uint32_t read32(void *p,uintptr_t a){struct mock*m=p;assert(a>=0x2ac60000&&a<0x2ac6022c);return m->r[(a-0x2ac60000)/4];}
static void write32(void *p,uintptr_t a,uint32_t v){
 struct mock*m=p;unsigned o=(unsigned)(a-0x2ac60000);m->n++;
 assert(o<0x22c);
 if(o==0x1c)m->r[o/4]&=~v;else m->r[o/4]=v;
 if(o==0x10||o==0x14){
  assert(m->r[0]&8);assert(m->r[0x18/4]==(o==0x10?68u:72u));
  if(m->fault==1)m->r[7]|=64;
  else if(m->fault!=2)m->r[7]|=(o==0x10?4u:8u);
 }
 if(o==0&&(v&16)&&m->fault!=3)m->r[7]|=32;
}
static uint64_t tick(void*p){struct mock*m=p;if(!m->frozen)m->now++;return m->now;}
static int lock(void*p){((struct mock*)p)->locks++;return 0;}
static void unlock(void*p){((struct mock*)p)->unlocks++;}
static int lines(void*p){return !((struct mock*)p)->low;}
static void setup(struct i3_live*s,struct mock*m){
 struct i3_port p={m,read32,write32,tick,lock,unlock,lines};
 memset(s,0,sizeof(*s));memset(m,0,sizeof(*m));m->r[0]=5u<<16;
 assert(i3_init(s,&p,false)==-EAGAIN);assert(!m->n);
 assert(!i3_init(s,&p,true));assert(!i3_timing(s));
}
int main(void){
 struct i3_live s;struct mock m;uint8_t v;unsigned n;int f;
 setup(&s,&m);printf("timing clkdiv=%08x con=%08x\n",m.r[1],m.r[0]);
 v=0x83;assert(!i3_xfer(&s,false,2,&v,100));assert(m.r[0x100/4]==0x830220);
 m.r[0x200/4]=0xab;v=0;assert(!i3_xfer(&s,true,2,&v,100)&&v==0xab);
 assert(!s.held&&!s.active&&m.locks==m.unlocks&&m.r[6]==0);
 for(f=1;f<=3;f++){
  setup(&s,&m);m.fault=f;v=0x55;
  assert(i3_xfer(&s,true,2,&v,30)==(f==1?-ENXIO:-ETIMEDOUT));assert(v==0x55&&s.poisoned);
  n=m.n;assert(i3_xfer(&s,true,2,&v,30)==-EBUSY&&m.n==n);
  if(f==3){assert(s.held&&s.active);m.fault=0;assert(!i3_cleanup(&s)&&!s.held);}
  else assert(!s.held);
 }
 setup(&s,&m);m.fault=2;m.frozen=true;assert(i3_xfer(&s,true,0,&v,30)==-ETIMEDOUT);
 setup(&s,&m);m.r[0]|=1;n=m.n;assert(i3_xfer(&s,false,0,&v,30)==-EBUSY&&m.n==n);
 setup(&s,&m);m.low=true;n=m.n;assert(i3_xfer(&s,false,0,&v,30)==-EBUSY&&m.n==n);
 assert(i3_gpio_lines(0x010219c8,0x3000)==1);
 assert(i3_gpio_lines(0x010219c8,0x1000)==0);
 assert(i3_gpio_lines(0,0x3000)==-ENODEV);
 puts("PASS actual live C: TX RX NAK data-timeout STOP-timeout cleanup frozen-clock busy lines GPIO; synthetic only");return 0;
}
