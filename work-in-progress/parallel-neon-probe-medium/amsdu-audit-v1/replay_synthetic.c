/* Synthetic branch fixtures only. No captured payload/PN is available. */
#include "skw_wifi_amsdu.h"
#include <assert.h>
#include <stdio.h>
static struct skw_amsdu_rx a;
static struct skw_data_replay r;
static const uint8_t own[6]={2,0,0,0,0,1};
static unsigned delivered;
static int deliver(const uint8_t *p,size_t n) {(void)p;assert(n==98);delivered++;return 0;}
static void reset(void) {
  uint8_t zero[6]={0};memset(&a,0,sizeof(a));delivered=0;
  assert(skw_data_begin(&r,true,zero,zero)==0);
}
static void fixture(uint8_t p[120],unsigned pn,unsigned flags,unsigned index) {
  memset(p,0,120);skw_eap_put16(p,116);p[2]=0x3f;p[3]=7;
  p[4]=(uint8_t)flags;skw_eap_put16(p+8,7);skw_eap_put16(p+10,0x6a04);
  skw_eap_put16(p+12,(uint16_t)pn);skw_eap_put16(p+16,92);
  p[18]=74;p[19]=(uint8_t)index;
  memcpy(p+22,own,6);p[34]=8;p[35]=0;
}
static int receive(uint8_t p[120],uint64_t now) {
 return skw_amsdu_receive(&a,&r,p,120,0,0,own,now,deliver);
}
int main(void) {
 uint8_t p[120];struct skw_data_view v;
 reset();fixture(p,10,0x76,1);
 assert(skw_data_inspect(p,120,0,0,own,&r,&v)==0);
 assert(!v.amsdu&&v.first&&v.last&&v.tid==6&&!v.multicast&&v.length==98);
 assert(v.sequence==7&&v.index==1&&v.pn==10);
 assert(receive(p,0)==0&&delivered==1&&r.unicast[6]==10);
 assert(receive(p,1)==-EACCES&&delivered==1);
 puts("synthetic committed-floor equality -> EACCES, inspect=0, amsdu=0");
 reset();fixture(p,9,0x76,1);r.unicast[6]=10;
 assert(receive(p,0)==-EACCES&&!delivered);
 puts("synthetic committed-floor greater -> EACCES");
 reset();fixture(p,11,0x3e,1);assert(receive(p,0)==0);
 assert(a.pending[0][6].active&&r.unicast[6]==0);
 fixture(p,10,0x76,1);assert(receive(p,1)==-EACCES&&!delivered);
 assert(r.unicast[6]==0&&a.pending[0][6].pn==11);
 assert(receive(p,1000)==-EACCES&&!delivered);
 puts("synthetic newer pending group -> EACCES even at age1000ms (non-AMSDU path precedes expiry)");
 reset();fixture(p,10,0x3e,1);assert(receive(p,0)==0);
 fixture(p,10,0x5e,2);assert(receive(p,1)==0);
 assert(a.complete==1&&a.subframes==2&&delivered==2);
 fixture(p,10,0x76,1);assert(receive(p,2)==-EACCES);
 assert(a.complete==1&&a.subframes==2&&delivered==2);
 puts("synthetic complete1/subframes2 plus non-AMSDU floor rejection is possible, NOT captured-frame replay");
 reset();fixture(p,10,0x76,1);r.pn_reuse=false;
 assert(skw_data_inspect(p,120,0,0,own,&r,&v)!=0);
 puts("PASS actual header implementation; all PN/addresses/payload synthetic; no hardware");
}
