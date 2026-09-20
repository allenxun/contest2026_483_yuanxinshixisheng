#define main gain_baseline_main
#include "test_gain_input.c"
#undef main
int main(void)
{
 struct kd_codec c;struct mock m;uint8_t before[256];unsigned calls;
 CHECK(gain_baseline_main()==0);
 init(&c,&m);memcpy(before,m.regs,sizeof before);
 CHECK(kd_stop(&c,1000)==0);m.calls=0;
 CHECK(kd_prepare_adc_variant(&c,32,KD_ADC_PGA24,1000)==0);
 calls=m.calls;CHECK(c.state==KD_PREPARED && m.regs[0x09]==0x88);
 before[0x09]=0x88;CHECK(memcmp(before,m.regs,sizeof before)==0);
 CHECK(!m.amp && !m.amp_on && !c.amp_armed);
 CHECK(kd_prepare_adc_variant(&c,32,KD_ADC_PGA24,1000)==-EBUSY);
 for(unsigned f=1;f<=calls;f++){
  init(&c,&m);CHECK(kd_stop(&c,1000)==0);m.calls=0;m.fail=f;
  CHECK(kd_prepare_adc_variant(&c,32,KD_ADC_PGA24,1000)==-EIO);
  CHECK(c.state==KD_FAULT && !m.amp_on && !c.amp_armed);
 }
 printf("PGA24 checks=%u PASS; mocks only, acoustic quality not tested\n",checks);
 return 0;
}
