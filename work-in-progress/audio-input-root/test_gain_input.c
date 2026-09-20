#include "codec_duplex.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct mock {uint64_t now;unsigned calls,fail,wrong,expire,amp_on;bool amp;uint8_t regs[256];};
static unsigned checks;
#define CHECK(x) do{assert(x);checks++;}while(0)
static uint64_t now(void*p){return ((struct mock*)p)->now;}
static int step(struct mock*m){m->calls++;if(m->calls==m->expire)m->now=1000;return m->calls==m->fail?-EIO:0;}
static int wr(void*p,uint8_t a,uint8_t r,uint8_t v,uint64_t d){
 struct mock*m=p;(void)d;CHECK(a==0x10);CHECK(!m->amp);
 if(step(m))return -EIO;
 m->regs[r]=v;return 0;
}
static int rd(void*p,uint8_t a,uint8_t r,uint8_t*v,uint64_t d){
 struct mock*m=p;(void)d;CHECK(a==0x10);
 if(step(m))return -EIO;
 *v=m->regs[r];if(m->calls==m->wrong)*v^=0x01;return 0;
}
static int delay(void*p,unsigned ms,uint64_t d){(void)d;((struct mock*)p)->now+=ms;return 0;}
static int amp(void*p,bool on,uint64_t d){struct mock*m=p;(void)d;m->amp_on+=on?1u:0u;if(step(m))return -EIO;m->amp=on;return 0;}
static int ready(void*p,unsigned b,uint32_t m,uint32_t s,bool c,bool t,uint64_t d){(void)p;(void)b;(void)m;(void)s;(void)c;(void)t;(void)d;return 0;}
static int quiet(void*p,uint64_t d){(void)p;(void)d;return 0;}
static void init(struct kd_codec*c,struct mock*m){
 struct kd_port p={m,now,wr,rd,delay,amp,ready,quiet};
 memset(m,0,sizeof(*m));CHECK(kd_bind(c,&p)==0);CHECK(kd_prepare(c,32,1000)==0);
 m->calls=0;CHECK(m->regs[0x1a]==48 && m->regs[0x1b]==48);
}
int main(void){
 struct kd_codec c;struct mock m;uint8_t before[256];
 for(unsigned g=0;g<=24;g+=6){
  init(&c,&m);memcpy(before,m.regs,sizeof before);
  CHECK(kd_set_playback_gain(&c,g,1000)==0);CHECK(c.state==KD_PREPARED);
  CHECK(m.regs[0x1a]==48u-2u*g && m.regs[0x1b]==48u-2u*g);
  before[0x1a]=m.regs[0x1a];before[0x1b]=m.regs[0x1b];
  CHECK(memcmp(before,m.regs,sizeof before)==0);CHECK(!m.amp && !m.amp_on && !c.amp_armed);CHECK(m.calls==5);
 }
 for(unsigned f=1;f<=5;f++){
  init(&c,&m);m.fail=f;CHECK(kd_set_playback_gain(&c,6,1000)==-EIO);
  CHECK(c.state==KD_FAULT && !m.amp && !m.amp_on && !c.amp_armed);
  CHECK(kd_arm(&c,false,true,1000)==-EBUSY);
 }
 for(unsigned f=3;f<=5;f+=2){
  init(&c,&m);m.wrong=f;CHECK(kd_set_playback_gain(&c,6,1000)==-EIO);CHECK(c.state==KD_FAULT && !m.amp_on);
 }
 for(unsigned f=1;f<=5;f++){
  init(&c,&m);m.expire=f;CHECK(kd_set_playback_gain(&c,6,1000)==-ETIMEDOUT);
  CHECK(c.state==KD_FAULT && !m.amp && !m.amp_on && !c.amp_armed);
  CHECK(kd_arm(&c,false,true,1100)==-EBUSY);
 }
 init(&c,&m);CHECK(kd_set_playback_gain(&c,1,1000)==-EINVAL);CHECK(kd_set_playback_gain(&c,30,1000)==-EINVAL);CHECK(m.calls==0 && c.state==KD_PREPARED);
 CHECK(kd_set_playback_gain(NULL,6,1000)==-EINVAL);
 for(int state=KD_OFF;state<=KD_FAULT;state++)if(state!=KD_PREPARED){
  init(&c,&m);c.state=(enum kd_state)state;CHECK(kd_set_playback_gain(&c,6,1000)==-EBUSY);CHECK(m.calls==0);
 }
 init(&c,&m);c.busy=true;CHECK(kd_set_playback_gain(&c,6,1000)==-EBUSY);CHECK(m.calls==0);
 init(&c,&m);CHECK(kd_set_playback_gain(&c,6,m.now)==-ETIMEDOUT);CHECK(c.state==KD_FAULT && m.calls==0 && !m.amp_on);
 init(&c,&m);m.now=0;CHECK(kd_set_playback_gain(&c,6,1000)==-EIO);CHECK(c.state==KD_FAULT && !m.amp_on);
 printf("gain checks=%u PASS (mock GPIO/I2C only)\n",checks);return 0;
}
