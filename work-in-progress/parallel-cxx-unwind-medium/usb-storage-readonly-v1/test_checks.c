#include "msc_read_checks.h"
#include <assert.h>
#include <stdio.h>

int main(void)
{
  uint8_t csw[13] = {0x55,0x53,0x42,0x53,7,0,0,0,0,0,0,0,0};
  assert(k7msc_capacity10_check(99999,512)==0);
  assert(k7msc_capacity10_check(UINT32_MAX,512)<0);
  assert(k7msc_capacity10_check(99,65536)<0);
  assert(k7msc_read10_check(100000,512,0,8)==0);
  assert(k7msc_read10_check(100000,512,99999,1)==0);
  assert(k7msc_read10_check(100000,4096,0,1)==0);
  assert(k7msc_read10_check(100000,512,-1,1)<0);
  assert(k7msc_read10_check(100000,512,99999,2)<0);
  assert(k7msc_read10_check(100000,512,0,9)<0);
  assert(k7msc_read10_check(100000,512,0,65536)<0);
  assert(k7msc_read10_check(100000,512,0,0)<0);
  assert(k7msc_read10_check(UINT64_MAX,512,0,1)<0);
  assert(k7msc_csw_check(csw,13,7)==0);
  assert(k7msc_csw_check(NULL,13,7)<0);
  assert(k7msc_csw_check(csw,12,7)<0);
  assert(k7msc_csw_check(csw,-1,7)<0);
  assert(k7msc_csw_check(csw,13,8)<0);
  csw[0]=0; assert(k7msc_csw_check(csw,13,7)<0); csw[0]=0x55;
  csw[8]=1; assert(k7msc_csw_check(csw,13,7)<0); csw[8]=0;
  csw[12]=1; assert(k7msc_csw_check(csw,13,7)<0);
  puts("PASS 20 C helper checks; synthetic host only");
  return 0;
}
