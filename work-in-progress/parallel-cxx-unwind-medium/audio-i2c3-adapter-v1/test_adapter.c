#include "adapter.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
/* Abstract mock register bank, NOT RK3576 register addresses/bit encodings. */
struct mock { uint32_t regs[4]; uint64_t time; bool locked,read,stalled,badstop,shortio; unsigned polls,unlocks,begins; int err; };
static uint64_t now(void *p){return ((struct mock *)p)->time;}
static int lock(void *p){struct mock*m=p;if(m->locked)return -EBUSY;m->locked=true;return 0;}
static void unlock(void*p){struct mock*m=p;assert(m->locked);m->locked=false;m->unlocks++;}
static int begin(void*p,bool read,uint8_t addr,uint8_t reg,uint8_t value){struct mock*m=p;assert(m->locked && addr==0x10);m->begins++;m->read=read;m->regs[0]=1;m->regs[1]=reg;m->regs[2]=value;return 0;}
static int poll(void*p,size_t*tx,size_t*rx,uint8_t*v){struct mock*m=p;m->polls++;if(m->err)return m->err;if(m->stalled)return 0;*tx=m->read?1:2;*rx=m->read?1:0;if(m->shortio)*tx=0;*v=0x5a;m->regs[3]=1;return 1;}
static int stop(void*p){struct mock*m=p;if(m->badstop)return -EIO;m->regs[0]=0;return 0;}
static int idle(void*p){return ((struct mock*)p)->regs[0]==0;}
static void fresh(struct ka_adapter*a,struct mock*m,struct ka_backend*b){memset(a,0,sizeof(*a));memset(m,0,sizeof(*m));*b=(struct ka_backend){m,now,lock,unlock,begin,poll,stop,idle};}
int main(void){
 struct ka_adapter a={0};struct mock m;struct ka_backend b;struct kc_io_result r;uint8_t v=0,bytes[]={1,2};unsigned checks=0;
 fresh(&a,&m,&b);assert(ka_init(&a,&b,KC_HARDWARE)==KC_NOT_READY&&!m.begins);checks++;
 assert(ka_init(&a,&b,KC_SIMULATION)==KC_OK);r=ka_read(&a,0x10,1,&v,100);assert(!r.error&&r.tx_done==1&&r.rx_done==1&&v==0x5a&&!a.leased);checks++;
 r=ka_write(&a,0x10,bytes,2,100);assert(!r.error&&r.tx_done==2&&!r.rx_done&&m.regs[2]==2);checks++;
 assert(ka_init(&a,&b,KC_SIMULATION)==KC_BUSY);checks++;
 r=ka_read(&a,0x11,1,&v,100);assert(r.error==-EINVAL&&m.begins==2);checks++;
 r=ka_write(&a,0x10,bytes,1,100);assert(r.error==-EINVAL);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.locked=true;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-EBUSY&&!m.begins);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.err=-ENXIO;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-ENXIO&&a.poisoned&&!a.leased&&m.unlocks==1);checks++;
 assert(ka_read(&a,0x10,1,&v,100).error==-EBUSY&&m.begins==1);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.badstop=true;r=ka_write(&a,0x10,bytes,2,100);assert(r.error&&a.leased&&m.locked&&!m.unlocks);checks++;
 m.badstop=false;assert(!ka_cleanup(&a,200)&&!a.leased&&m.unlocks==1&&a.poisoned);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.stalled=true;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-ETIMEDOUT&&m.polls==KA_POLL_LIMIT&&!a.leased);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.time=100;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-ETIMEDOUT&&!m.begins&&!a.leased);checks++;
 fresh(&a,&m,&b);m.time=10;assert(!ka_init(&a,&b,KC_SIMULATION));m.time=9;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-EIO&&!m.begins);checks++;
 fresh(&a,&m,&b);assert(!ka_init(&a,&b,KC_SIMULATION));m.shortio=true;v=0x33;r=ka_read(&a,0x10,1,&v,100);assert(r.error==-EIO&&v==0x33&&a.poisoned);checks++;
 printf("PASS %u adapter lifecycle/mock-register checks; hardware unavailable\n",checks);return 0;
}
