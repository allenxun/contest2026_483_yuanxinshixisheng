#define main gain_regression_main
#include "test_gain.c"
#undef main
int main(void){
 struct kd_codec c;struct mock m;uint8_t before[256];
 CHECK(gain_regression_main()==0);
 init(&c,&m);memcpy(before,m.regs,sizeof before);
 CHECK(kd_set_playback_max(&c,1000)==0);
 CHECK(c.state==KD_PREPARED && !m.amp && !m.amp_on && !c.amp_armed);
 CHECK(m.regs[0x1a]==0 && m.regs[0x1b]==0 && m.regs[0x30]==33 && m.regs[0x31]==33);
 before[0x1a]=0;before[0x1b]=0;before[0x30]=33;before[0x31]=33;
 CHECK(memcmp(before,m.regs,sizeof before)==0 && m.calls==9);
 for(unsigned f=1;f<=9;f++){
  init(&c,&m);m.fail=f;CHECK(kd_set_playback_max(&c,1000)==-EIO);
  CHECK(c.state==KD_FAULT && !m.amp && !m.amp_on && !c.amp_armed);
  CHECK(kd_arm(&c,false,true,1100)==-EBUSY);
  init(&c,&m);m.expire=f;CHECK(kd_set_playback_max(&c,1000)==-ETIMEDOUT);
  CHECK(c.state==KD_FAULT && !m.amp && !m.amp_on && !c.amp_armed);
 }
 for(unsigned f=3;f<=9;f+=2){
  init(&c,&m);m.wrong=f;CHECK(kd_set_playback_max(&c,1000)==-EIO);CHECK(c.state==KD_FAULT && !m.amp_on);
 }
 for(int state=KD_OFF;state<=KD_FAULT;state++)if(state!=KD_PREPARED){
  init(&c,&m);c.state=(enum kd_state)state;CHECK(kd_set_playback_max(&c,1000)==-EBUSY);CHECK(m.calls==0);
 }
 init(&c,&m);c.busy=true;CHECK(kd_set_playback_max(&c,1000)==-EBUSY);CHECK(m.calls==0);
 init(&c,&m);CHECK(kd_set_playback_max(&c,m.now)==-ETIMEDOUT);CHECK(c.state==KD_FAULT && m.calls==0);
 CHECK(kd_set_playback_max(NULL,1000)==-EINVAL);
 printf("max cumulative checks=%u PASS (mock only)\n",checks);return 0;
}
