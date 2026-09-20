/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_wifi_data.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
  const uint8_t own[]={2,0,0,0,0,1};uint8_t rsc[6]={0};
  struct skw_data_replay replay;struct skw_data_view view;
  uint8_t frame[82]={78,0,0x3f,7},copy[82],out[100];size_t length;
  frame[4]=4;skw_eap_put16(frame+10,0x6204);frame[12]=1;
  skw_eap_put16(frame+16,54);frame[18]=74;
  memcpy(frame+22,own,6);frame[34]=8;frame[35]=0;
  assert(!skw_data_begin(&replay,true,rsc,rsc));
  assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view));
  assert(view.length==60 && view.ethernet==frame+22 && view.tid==6 && view.pn==1);
  assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-EACCES);
  frame[12]=2;assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view));
  frame[12]=0;assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-EACCES);
  frame[12]=3;
  for(size_t n=0;n<sizeof(frame);n++)
    {assert(!skw_data_begin(&replay,true,rsc,rsc));assert(skw_data_decode(frame,n,0,0,own,&replay,&view));}
  for(unsigned i=0;i<7;i++)
    {
      memcpy(copy,frame,sizeof(copy));assert(!skw_data_begin(&replay,true,rsc,rsc));
      switch(i){case 0:copy[18]=51;break;case 1:copy[18]=255;break;
        case 2:copy[16]=255;copy[17]=255;break;case 3:copy[4]|=8;break;
        case 4:copy[11]|=0x90;break;case 5:copy[22]=4;break;case 6:copy[10]|=0x10;break;}
      assert(skw_data_decode(copy,sizeof(copy),0,0,own,&replay,&view));
    }
  /* Independent multicast replay domain, initial GTK RSC respected. */
  memset(frame+22,255,6);frame[11]|=4;rsc[0]=3;
  assert(!skw_data_begin(&replay,true,rsc,rsc));
  assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-EACCES);
  frame[12]=4;assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view) && view.multicast);
  rsc[4]=1;assert(skw_data_begin(&replay,true,rsc,rsc)==-ENOTSUP);
  assert(!skw_data_encode(7,1,frame+22,60,out,sizeof(out),&length));
  assert(length==68 && skw_eap_u16(out)==0x700 && skw_eap_u16(out+2)==0x103c && out[4]==8 && !out[5]);
  /* Normal descriptor keeps cipher and full 48-bit PN independently of the
   * SDIO header; zero high PN bits must not be assumed on this path. */
  uint8_t full[86]={82,0,0x3f,7};
  memcpy(full+4,frame,20);full[4]=0;full[5]=8;
  skw_eap_put16(full+6,54);full[8]=4;full[15]=0x62;
  memset(full+16,0,6);full[20]=1;full[22]=74;
  memcpy(full+26,own,6);full[38]=8;
  memset(rsc,0,6);assert(!skw_data_begin(&replay,false,rsc,rsc));
  assert(!skw_data_decode(full,sizeof(full),0,0,own,&replay,&view));
  assert(view.pn==UINT64_C(0x100000000) && view.length==60);
  full[5]=0;assert(skw_data_decode(full,sizeof(full),0,0,own,&replay,&view)==-EACCES);
  /* TID replay counters are independent, and failed copies never become an
   * apparent successful TX or expose an uninitialized output length. */
  frame[11]=0x62;memcpy(frame+22,own,6);frame[12]=1;
  assert(!skw_data_begin(&replay,true,rsc,rsc));
  assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view));
  frame[11]=0x52;assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view));
  frame[11]=0x62;assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-EACCES);
  length=99;assert(skw_data_encode(0,0,frame+22,60,out,67,&length)==-ENOSPC && !length);
  assert(skw_data_encode(32,0,frame+22,60,out,sizeof(out),&length)==-EINVAL);
  /* Real K7 receive flags were 0x76: independent MSDU in an AMPDU. */
  frame[4]=0x76;frame[12]=2;frame[11]=0x0a;
  assert(!skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view));
  assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-EACCES);
  frame[12]=3;frame[4]|=8;
  assert(skw_data_decode(frame,sizeof(frame),0,0,own,&replay,&view)==-ENOTSUP);
  puts("PASS: Ethernet descriptor bounds, peer/destination, per-TID unicast/multicast PN replay, RSC overflow and encrypted TX layout");
}
