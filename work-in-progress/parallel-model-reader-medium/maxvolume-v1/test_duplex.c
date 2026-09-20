#include "codec_duplex.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
struct mock {uint8_t regs[256];unsigned calls,fail_at,amp_on,joins,delays;uint64_t now;bool amp,corrupt,early,late;struct kd_codec *codec;};
static unsigned checks;
static int hit(struct mock*m){++m->calls;if(m->late)m->now+=10000;return m->calls==m->fail_at?-EIO:0;}
static uint64_t now(void*v){return ((struct mock*)v)->now;}
static int wr(void*v,uint8_t a,uint8_t r,uint8_t b,uint64_t d){
 struct mock*m=v;(void)d;assert(a==0x10 && r<=0x34);m->regs[r]=b;return hit(m);
}
static int rd(void*v,uint8_t a,uint8_t r,uint8_t*b,uint64_t d){
 struct mock*m=v;(void)d;assert(a==0x10);*b=m->regs[r];if(m->corrupt)*b^=0xff;return hit(m);
}
static int delay(void*v,unsigned ms,uint64_t d){struct mock*m=v;(void)d;++m->delays;if(!m->early)m->now+=ms;return hit(m);}
static int amp(void*v,bool on,uint64_t d){struct mock*m=v;(void)d;m->amp=on;if(on)++m->amp_on;return hit(m);}
static int ready(void*v,unsigned bits,uint32_t mclk,uint32_t bclk,bool cap,bool play,uint64_t d){
 struct mock*m=v;(void)cap;(void)play;(void)d;assert(bits==16 || bits==32);assert(mclk==4096000 && bclk==32000u*bits);
 if(m->codec){assert(kd_prepare(m->codec,bits,d)==-EBUSY);}
 return hit(m);
}
static int join(void*v,uint64_t d){struct mock*m=v;(void)d;++m->joins;return hit(m);}
static void setup(struct kd_codec*c,struct mock*m){
 struct kd_port p={m,now,wr,rd,delay,amp,ready,join};memset(m,0,sizeof(*m));m->now=1;m->codec=c;assert(kd_bind(c,&p)==0);
}
static void ck(bool v){++checks;assert(v);}
int main(void){
 struct kd_codec c;struct mock m;unsigned prepare_calls,activate_calls;
 for(unsigned bits=16;bits<=32;bits+=16){
  setup(&c,&m);ck(kd_prepare(&c,bits,1000)==0);prepare_calls=m.calls;
  ck(m.regs[5]==0 && m.regs[6]==0 && m.regs[7]==0x7c && m.regs[3]==0);
  ck(c.state==KD_PREPARED && !m.amp && m.regs[0x19]==6 && m.regs[0x0f]==0x34);
  ck(m.regs[0x0a]==0xf0 && m.regs[0x0b]==0x82);
  ck(m.regs[0x0c]==(bits==16?0x0c:0x10) && m.regs[0x17]==(bits==16?0x18:0x20));
  ck(m.regs[0x12]==0 && m.regs[0x16]==0 && m.regs[0x09]==0x44);
  ck(m.regs[0x1a]==0x30 && m.regs[0x1b]==0x30 && m.regs[0x30]==0x14 && m.regs[0x31]==0x14);
  ck(kd_activate(&c,true,true,1000)==0);activate_calls=m.calls-prepare_calls;ck(m.amp && m.amp_on==1);
  ck(kd_mute(&c,1000)==0 && !m.amp && c.state==KD_ACTIVE);
  ck(kd_activate(&c,true,false,1000)==0 && !m.amp);
  ck(kd_stop(&c,1000)==0 && c.state==KD_OFF && m.joins==1 && !m.amp);
  ck(m.regs[3]==0xfc && m.regs[4]==0xc0 && m.regs[2]==0xf3);
  for(unsigned i=1;i<=prepare_calls;i++){
   setup(&c,&m);m.fail_at=i;ck(kd_prepare(&c,bits,1000)==-EIO);ck(c.state==KD_FAULT && m.calls==i && !m.amp);
   m.fail_at=0;ck(kd_stop(&c,2000)==0 && c.state==KD_OFF);
  }
  for(unsigned i=1;i<=activate_calls;i++){
   setup(&c,&m);ck(kd_prepare(&c,bits,1000)==0);m.fail_at=m.calls+i;
   ck(kd_activate(&c,true,true,1000)==-EIO && c.state==KD_FAULT && !m.amp);
   m.fail_at=0;ck(kd_stop(&c,2000)==0);
  }
 }
 setup(&c,&m);ck(kd_prepare(&c,24,1000)==-EINVAL && m.calls==0);
 setup(&c,&m);m.corrupt=true;ck(kd_prepare(&c,32,1000)==-EIO && c.state==KD_FAULT);
 setup(&c,&m);m.early=true;ck(kd_prepare(&c,32,1000)==-EIO);
 setup(&c,&m);m.late=true;ck(kd_prepare(&c,32,1000)==-ETIMEDOUT && m.calls==1);
 setup(&c,&m);ck(kd_prepare(&c,32,1)==-ETIMEDOUT && m.calls==0);
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);ck(kd_activate(&c,true,false,1000)==0 && m.amp_on==0);
 /* Stop quiesce failure retains ownership; retry succeeds. */
 m.fail_at=m.calls+6;ck(kd_stop(&c,1000)==-EIO && c.state==KD_FAULT);m.fail_at=0;ck(kd_stop(&c,2000)==0);
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);
 unsigned before=m.calls;ck(kd_stop(&c,1000)==0);unsigned stop_calls=m.calls-before;
 for(unsigned i=1;i<=stop_calls;i++){
  setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);m.fail_at=m.calls+i;
  ck(kd_stop(&c,1000)==-EIO && c.state==KD_FAULT);
  m.fail_at=0;ck(kd_stop(&c,2000)==0 && c.state==KD_OFF);
 }
 /* PIO prestart arm must not enable amp; poststart enable has no I2C/delay. */
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);ck(kd_arm(&c,true,true,1000)==0);
 ck(!m.amp && m.amp_on==0 && c.amp_armed);
 unsigned armed_calls=m.calls,armed_delays=m.delays;uint64_t armed_time=m.now;
 ck(kd_enable_amp(&c,1000)==0 && m.amp && !c.amp_armed);
 ck(m.calls==armed_calls+1 && m.delays==armed_delays && m.now==armed_time);
 ck(kd_enable_amp(&c,1000)==-EINVAL);ck(kd_stop(&c,1000)==0);
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);ck(kd_arm(&c,true,false,1000)==0);
 ck(kd_enable_amp(&c,1000)==-EINVAL && !m.amp);ck(kd_stop(&c,1000)==0);
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);ck(kd_arm(&c,false,true,1000)==0);
 m.fail_at=m.calls+1;ck(kd_enable_amp(&c,1000)==-EIO && !m.amp && c.state==KD_FAULT);
 m.fail_at=0;ck(kd_stop(&c,2000)==0);
 setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);ck(kd_arm(&c,false,true,1000)==0);
 ck(kd_enable_amp(&c,m.now)==-ETIMEDOUT && !m.amp && !c.amp_armed);
 ck(kd_stop(&c,2000)==0);
 /* Explicit ADC comparisons differ only in selected register from baseline. */
 uint8_t baseline[256];setup(&c,&m);ck(kd_prepare(&c,32,1000)==0);memcpy(baseline,m.regs,sizeof baseline);
 ck(kd_stop(&c,2000)==0);
 for(unsigned mode=1;mode<=2;mode++){
  setup(&c,&m);ck(kd_prepare_adc_variant(&c,32,(enum kd_adc_variant)mode,1000)==0);
  unsigned mode_calls=m.calls;
  for(unsigned r=0;r<256;r++){
   uint8_t expected=baseline[r];
   if(mode==1 && r==1)expected=0x40;
   if(mode==2 && r==0)expected=0x35;
   ck(m.regs[r]==expected);
  }
  ck(kd_prepare_adc_variant(&c,32,KD_ADC_BASELINE,1000)==-EBUSY);
  ck(kd_stop(&c,2000)==0);
  for(unsigned f=1;f<=mode_calls;f++){
   setup(&c,&m);m.fail_at=f;
   ck(kd_prepare_adc_variant(&c,32,(enum kd_adc_variant)mode,1000)==-EIO && c.state==KD_FAULT);
   m.fail_at=0;ck(kd_stop(&c,2000)==0);
  }
 }
 setup(&c,&m);ck(kd_prepare_adc_variant(&c,32,(enum kd_adc_variant)99,1000)==-EINVAL && m.calls==0);
 printf("PASS %u checks: prepare/activate/mute/stop,16/32-bit profiles,all prepare+activate callback faults,readback mismatch,delay/timeout,reentry,cleanup retry; MOCK ONLY\n",checks);
 return 0;
}
