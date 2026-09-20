/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_wifi_join.h"
#include <assert.h>
#include <stdio.h>
static const uint8_t own[6]={2,1,2,3,4,5},ap[6]={4,0xe7,0x95,0xac,0xa,0xd2};
int main(void)
{
  uint8_t b[1200],frame[80]={149,1,0xd0,0xff,30,0,0,0};
  const uint8_t ie[]={0,6,'L','a','n','s','e','e'};
  size_t n;struct skw_mgmt_result event;struct skw_join_reply reply;
  memset(b,0xa5,sizeof(b));
  assert(!skw_join_encode(149,1,160,0x1511,ap,ie,sizeof(ie),b+1,1198,&n));
  assert(n==33 && b[0]==0xa5 && b[34]==0xa5);
  assert(b[1]==149 && b[2]==149 && b[5]==1);
  assert(b[6]==0xa0 && b[7]==0 && b[8]==0x11 && b[9]==0x15);
  assert(!memcmp(b+12,ap,6) && b[20]==25 && b[22]==8);
  assert(!memcmp(b+26,ie,sizeof(ie)));
  assert(skw_join_encode(149,1,160,0x1511,ap,ie,7,b,1200,&n)==-EPROTO && n==0);
  assert(skw_join_encode(149,1,160,0x1511,ap,ie,8,b,32,&n)==-ENOSPC);
  assert(skw_join_encode(149,1,160,0x1511,ap,NULL,8,b,1200,&n)==-EINVAL);
  assert(!skw_auth_open_encode(b+1,14));
  for(size_t i=1;i<15;i++)assert(!b[i]);
  assert(!skw_assoc_encode(ap,ie,sizeof(ie),b,1200,&n));
  assert(n==62 && !memcmp(b+38,ap,6) && b[50]==54 && b[52]==8);
  assert(!skw_join_reply_decode((const uint8_t[]){2,0,0,3},4,&reply));
  assert(reply.peer==2 && reply.multicast==3);
  assert(skw_join_reply_decode(b,3,&reply)==-EMSGSIZE);
  frame[8]=0xb0;memcpy(frame+12,own,6);memcpy(frame+18,ap,6);
  memcpy(frame+24,ap,6);frame[34]=2;
  assert(!skw_mgmt_decode(frame,38,own,ap,149,1,&event));
  assert(event.kind==SKW_MGMT_AUTH && !event.status && event.transaction==2);
  for(size_t i=0;i<38;i++)assert(skw_mgmt_decode(frame,i,own,ap,149,1,&event)<0);
  frame[12]^=1;
  assert(!skw_mgmt_decode(frame,38,own,ap,149,1,&event) && event.kind==SKW_MGMT_NONE);
  frame[12]^=1;frame[34]=3;
  assert(skw_mgmt_decode(frame,38,own,ap,149,1,&event)==-EPROTO);
  frame[8]=0x10;frame[34]=0;frame[36]=5;frame[37]=0xc0;
  assert(!skw_mgmt_decode(frame,38,own,ap,149,1,&event));
  assert(event.kind==SKW_MGMT_ASSOC && event.aid==5 && !event.status);
  frame[34]=17;
  assert(!skw_mgmt_decode(frame,38,own,ap,149,1,&event) && event.status==17);
  frame[9]=4;
  assert(skw_mgmt_decode(frame,38,own,ap,149,1,&event)==-EPROTO);
  assert(!skw_disconnect_encode(3,b,8) && b[0]==2 && b[2]==3);
  unsigned int seed=7;
  for(unsigned int j=0;j<20000;j++)
    {
      for(size_t i=0;i<sizeof(frame);i++)
        {seed=seed*1664525u+1013904223u;frame[i]=(uint8_t)(seed>>24);}
      (void)skw_mgmt_decode(frame,j%81,own,ap,149,1,&event);
    }
  puts("PASS SDK JOIN/AUTH/ASSOC wire offsets; response/status decoding; foreign-peer rejection; truncations; 20000 malformed frames");
  return 0;
}
