#include "skw_wifi_amsdu.h"
#include <assert.h>
#include <stdio.h>
int baseline(struct skw_amsdu_rx*,struct skw_data_replay*,const uint8_t*,uint64_t,int(*)(const uint8_t*,size_t));
static struct skw_amsdu_rx old_a,new_a;
static struct skw_data_replay old_r,new_r;
static struct skw_pn_diag diag;
static unsigned old_delivered,new_delivered,checks;
static const uint8_t own[6]={2,0,0,0,0,1};
static int old_delivery(const uint8_t*p,size_t n){(void)p;assert(n==98);old_delivered++;return 0;}
static int new_delivery(const uint8_t*p,size_t n){(void)p;assert(n==98);new_delivered++;return 0;}
static void reset(void) {
 uint8_t zero[6]={0};memset(&old_a,0,sizeof(old_a));memset(&new_a,0,sizeof(new_a));
 assert(!skw_data_begin(&old_r,true,zero,zero));assert(!skw_data_begin(&new_r,true,zero,zero));
 memset(&diag,0,sizeof(diag));old_delivered=new_delivered=0;
}
static int step(unsigned pn,unsigned sequence,unsigned flags,unsigned index,uint64_t time) {
 uint8_t p[120]={116,0,0x3f,7};p[4]=(uint8_t)flags;skw_eap_put16(p+8,(uint16_t)sequence);
 skw_eap_put16(p+10,0x6a04);skw_eap_put16(p+12,(uint16_t)pn);skw_eap_put16(p+16,92);
 p[18]=74;p[19]=(uint8_t)index;memcpy(p+22,own,6);p[34]=8;
 int before=baseline(&old_a,&old_r,p,time,old_delivery);
 int after=skw_amsdu_receive_diag(&new_a,&new_r,p,sizeof(p),0,0,own,time,new_delivery,&diag);
 assert(before==after&&old_delivered==new_delivered);
 assert(!memcmp(&old_a,&new_a,sizeof(old_a))&&!memcmp(&old_r,&new_r,sizeof(old_r)));
 checks++;return after;
}
int main(void) {
 reset();assert(!step(10,7,0x76,1,0));assert(step(10,7,0x76,1,1)==-EACCES);
 assert(diag.count==1&&diag.entries[0].reason==SKW_PN_FLOOR&&diag.entries[0].pn==10&&diag.entries[0].floor==10);
 assert(!diag.entries[0].pending_active&&!diag.entries[0].age_valid);
 assert(step(9,7,0x76,1,1000)==-EACCES&&diag.count==1&&diag.suppressed==1);
 assert(step(9,7,0x76,1,1001)==-EACCES&&diag.count==2);
 assert(step(9,7,0x76,1,900)==-EACCES&&diag.suppressed==2);
 for(unsigned i=2;i<20;i++)assert(step(9,7,0x76,1,1+1000*i)==-EACCES);
 assert(diag.count==16&&diag.full==4);
 diag.seen=diag.full=UINT_MAX;assert(step(9,7,0x76,1,25000)==-EACCES);
 assert(diag.seen==UINT_MAX&&diag.full==UINT_MAX);
 reset();assert(!step(11,7,0x3e,1,0));assert(step(10,7,0x76,1,1000)==-EACCES);
 assert(diag.entries[0].reason==SKW_PN_PENDING_NEWER&&diag.entries[0].pending_pn==11&&diag.entries[0].age_ms==1000);
 reset();assert(!step(11,7,0x3e,1,0));assert(step(11,8,0x5e,2,1)==-EACCES);
 assert(diag.entries[0].reason==SKW_PN_PENDING_TUPLE&&diag.entries[0].sequence==8&&diag.entries[0].pending_sequence==7);
 reset();assert(!step(11,7,0x3e,1,0));assert(step(11,7,0x3e,1,1)==-EACCES);
 assert(diag.entries[0].reason==SKW_PN_DUPLICATE_INDEX&&diag.entries[0].index==1&&diag.entries[0].bitmap==1);
 assert(!step(11,7,0x5e,2,2)&&new_a.complete==1&&new_delivered==2);
 reset();assert(!step(11,7,0x3e,1,100));assert(step(10,7,0x76,1,99)==-EACCES);
 assert(!diag.entries[0].age_valid&&diag.entries[0].age_ms==0);
 reset();assert(step(11,7,0x1e,2,0)==-EPROTO&&diag.count==0&&diag.seen==0);
 /* Deterministic mixed finite stream: compare all receiver state each step. */
 reset();unsigned seed=12345;
 for(unsigned i=0;i<3000;i++) {
  seed=seed*1664525u+1013904223u;
  const unsigned flags[4]={0x76,0x3e,0x1e,0x5e};
  step(1+(seed%200),(seed>>8)%32,flags[(seed>>16)%4],(seed>>20)%5,i);
 }
 printf("PASS differential steps=%u; four reasons, 16-record cap, 1000ms gate, saturation, age; record_bytes=%u storage_bytes=%u\n",checks,(unsigned)sizeof(struct skw_pn_record),(unsigned)sizeof(diag));
}
