#include "loopback_recipe.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
 struct lb_snapshot s={0};struct lb_recipe r;uint32_t restored;unsigned i,j;
 s.version=0x23073576;s.amp_low=s.common_clock_verified=1;
 s.txcr=s.rxcr=0x00400fff;s.fscr=0x0101f03f;s.ckr=0x18;
 s.txshift=s.rxshift=2;s.path=0xe4e4;
 assert(lb_plan(&s,&r)==0 && r.enabled==0x4e4e4);
 assert(lb_restore(&r,r.enabled,1,1,&restored)==0 && restored==s.path);
 assert(lb_restore(&r,r.enabled,0,1,&restored)==-2);
 assert(lb_restore(&r,r.enabled,1,0,&restored)==-2);
 s.common_clock_verified=0;assert(lb_plan(&s,&r)==-2 && !r.valid);
 s.common_clock_verified=1;s.dmacr=1u<<24;assert(lb_plan(&s,&r)==-3);
 s.dmacr=0;s.xfer=11;assert(lb_plan(&s,&r)==-3);
 s.xfer=0;s.rxfifo=1;assert(lb_plan(&s,&r)==-3);
 s.rxfifo=0;s.rxshift=0;assert(lb_plan(&s,&r)==-4);
 s.rxshift=2;s.path=0xabcde4e4;
 /* unrelated PATH upper bits are retained and restored independently */
 s.path&=~0x30000u;
 assert(lb_plan(&s,&r)==0);
 assert((r.enabled&~r.mask)==(s.path&~r.mask));
 assert(lb_restore(&r,r.enabled,1,1,&restored)==0 && restored==s.path);
 for(i=0;i<8;i++){assert(lb_marker(i)!=0);for(j=0;j<i;j++)assert(lb_marker(i)!=lb_marker(j));}
 assert(lb_marker(8)==lb_marker(0));
 puts("PASS recipe: gated profile, masked loop0 routing, restoration, unique sequence markers");
 puts("NOT TESTED: hardware loopback, FIFO bank assignment, duplex timing, audio quality");
 return 0;
}
