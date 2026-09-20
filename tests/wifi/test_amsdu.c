/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_wifi_amsdu.h"
#include <assert.h>
#include <stdio.h>
static struct skw_amsdu_rx assembly;
static struct skw_data_replay replay;
static const uint8_t own[6]={2,0,0,0,0,1};
static unsigned count;static uint8_t order[16];
static int deliver(const uint8_t *p,size_t n)
{assert(n==60 && count<16);order[count++]=p[14];return 0;}
static void reset(void)
{uint8_t zero[6]={0};memset(&assembly,0,sizeof(assembly));assert(!skw_data_begin(&replay,true,zero,zero));count=0;}
static int frame(unsigned pn,unsigned sequence,unsigned index,uint8_t flags,uint64_t time,bool supported)
{
  uint8_t p[82]={78,0,0x3f,7};p[4]=flags;skw_eap_put16(p+8,sequence);
  skw_eap_put16(p+10,0x0a04);skw_eap_put16(p+12,pn);
  skw_eap_put16(p+16,54);p[18]=74;p[19]=index;
  memcpy(p+22,own,6);p[34]=supported?8:0x86;p[35]=supported?6:0xdd;p[36]=index;
  return skw_amsdu_receive(&assembly,&replay,p,sizeof(p),0,0,own,time,deliver);
}
int main(void)
{
  reset();assert(!frame(1,42,0,0x3e,0,true));assert(!count && !replay.unicast[0]);
  assert(frame(1,42,0,0x3e,1,true)==-EACCES);
  assert(!frame(1,42,2,0x5e,2,true));assert(!count);
  assert(!frame(1,42,1,0x1e,3,true));assert(count==3 && replay.unicast[0]==1);
  assert(order[0]==0 && order[1]==1 && order[2]==2);
  assert(frame(1,42,0,0x3e,4,true)==-EACCES && count==3);
  reset();assert(frame(1,42,1,0x1e,0,true)==-EPROTO && !count);
  assert(!frame(1,42,0,0x3e,1,true));
  assert(frame(1,43,1,0x5e,2,true)==-EACCES && !count);
  assert(frame(2,42,1,0x5e,3,true)==-EPROTO && !count);
  assert(frame(1,42,8,0x5e,4,true)==-EPROTO && !count);
  assert(frame(1,42,1,0x5e,252,true)==-EPROTO && !count);
  /* Unsupported IPv6 subframes participate in completeness but are not sent
   * to the IPv4 stack; a pending aggregate cannot steal a newer replay PN. */
  reset();assert(!frame(1,42,0,0x3e,0,true));
  assert(!frame(1,42,1,0x1e,1,false));assert(!frame(1,42,2,0x5e,2,true));assert(count==2);
  assert(!frame(2,43,0,0x3e,3,true));
  assert(!frame(3,44,0,0x76,4,true));assert(count==3 && replay.unicast[0]==3);
  assert(frame(2,43,1,0x5e,5,true)==-EACCES && count==3);
  reset();assert(!frame(1,42,0,0x7e,0,true));assert(count==1 && replay.unicast[0]==1);
  reset();assert(!frame(1,42,0,0x3e,0,true));assert(!frame(1,42,3,0x1e,1,true));
  assert(frame(1,42,2,0x5e,2,true)==-EPROTO && !count);
  /* Actual descriptor sample: first flag 0x3e with index 1, not zero. */
  reset();assert(!frame(1,7,1,0x3e,0,true));assert(!count);
  assert(frame(1,7,2,0x3e,1,true)==-EPROTO && !count);
  assert(!frame(1,7,2,0x5e,2,true));assert(count==2 && order[0]==1 && order[1]==2);
  assert(assembly.complete==1 && assembly.subframes==2);
  assert(frame(1,7,1,0x3e,3,true)==-EACCES && count==2);
  reset();assert(!frame(1,8,1,0x3e,0,true));
  assert(frame(1,8,0,0x1e,1,true)==-EPROTO && !count);
  for(unsigned i=2;i<8;i++)assert(!frame(1,8,i,0x1e,i,true));
  assert(frame(1,8,9,0x5e,8,true)==-EPROTO && !count);
  assert(!frame(1,8,8,0x5e,9,true));assert(count==8 && order[7]==8);
  puts("PASS: AMSDU complete-before-delivery, ordered release, duplicate/replay, mixed PN/sequence, orphan, timeout, bounds and unsupported subframe filtering");
}
