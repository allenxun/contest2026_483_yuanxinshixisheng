/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_wifi_eapol.h"
#include <assert.h>
#include <stdio.h>
static const uint8_t own[]={0x60,0x48,0x9c,0xb5,0x17,0x1c};
static const uint8_t bssid[]={4,0xe7,0x95,0xac,0x0a,0x62};
int main(void)
{
 /* Only these 32 payload-prefix bytes were captured from id36. The rest
  * below is deliberately synthetic; this is NOT a captured WPA handshake. */
 const uint8_t prefix[]={0x74,0,0,5,0,0,4,0x6a,0,0,0,0,0x81,0,0x4a,1,0,0,
                        0x60,0x48,0x9c,0xb5,0x17,0x1c,4,0xe7,0x95,0xac,0x0a,0x62,0x88,0x8e};
 uint8_t frame[157]={0x99,0,0x3f,7},copy[157],tx[1100],bad[6]={0};
 struct skw_eapol_view view;size_t written;
 memcpy(frame+4,prefix,sizeof(prefix));
 frame[36]=2;frame[37]=3;frame[38]=0;frame[39]=117;
 assert(!skw_eapol_decode(frame,sizeof(frame),true,0,0,own,bssid,&view));
 assert(view.ethernet_offset==22 && view.ethernet_length==135 && view.length==121 && view.data==frame+36 && view.tid==6);
 uint8_t normal[161]={0x9d,0,0x3f,7};memcpy(normal+4,frame,sizeof(frame));normal[6]=0x81;normal[7]=0;
 assert(!skw_eapol_decode(normal,sizeof(normal),false,0,0,own,bssid,&view));
 assert(view.ethernet_offset==26 && view.length==121);
 for(size_t n=0;n<sizeof(frame);n++) assert(skw_eapol_decode(frame,n,true,0,0,own,bssid,&view));
 assert(skw_eapol_decode(frame,sizeof(frame),true,0,0,bad,bssid,&view)==-EACCES);
 assert(skw_eapol_decode(frame,sizeof(frame),true,0,0,own,bad,&view)==-EACCES);
 assert(skw_eapol_decode(frame,sizeof(frame),true,1,0,own,bssid,&view)==-EACCES);
 assert(skw_eapol_decode(frame,sizeof(frame),true,0,1,own,bssid,&view)==-EACCES);
 for(unsigned i=0;i<8;i++) {
   memcpy(copy,frame,sizeof(frame));
   switch(i) {
     case 0:copy[18]=51;break;          /* descriptor offset underflow */
     case 1:copy[18]=255;break;         /* frame beyond packet */
     case 2:copy[16]=255;copy[17]=255;break; /* advertised MSDU length */
     case 3:copy[4]|=8;break;           /* unsupported A-MSDU */
     case 4:copy[10]|=8;break;          /* fragmented MPDU */
     case 5:copy[38]=255;break;         /* EAPOL body beyond Ethernet */
     case 6:copy[34]=8;copy[35]=0;break;/* IP is not accepted as EAPOL */
     case 7:copy[3]=6;break;            /* wrong SDIO channel */
   }
   assert(skw_eapol_decode(copy,sizeof(copy),true,0,0,own,bssid,&view));assert(!view.data);
 }
 assert(!skw_eapol_encode(2,1,7,own,bssid,frame+36,121,tx,sizeof(tx),&written));
 assert(written==143 && skw_eap_u16(tx)==0x768 && skw_eap_u16(tx+2)==0x1087);
 assert(tx[4]==0x88 && tx[5]==0x8e && !tx[6] && !tx[7]);
 assert(!memcmp(tx+8,bssid,6) && !memcmp(tx+14,own,6) && !memcmp(tx+22,frame+36,121));
 for(size_t cap=0;cap<143;cap++) {written=999;assert(skw_eapol_encode(0,0,0,own,bssid,frame+36,121,tx,cap,&written)==-ENOSPC && !written);}
 assert(skw_eapol_encode(0,0,0,own,bssid,frame+36,4,tx,sizeof(tx),&written)==-EINVAL && !written);
 uint32_t random=0x626c6531;
 for(unsigned trial=0;trial<20000;trial++) {
   for(unsigned i=0;i<sizeof(copy);i++) {random=random*1664525u+1013904223u;copy[i]=random>>24;}
   skw_eapol_decode(copy,trial%158,trial&1,0,0,own,bssid,&view);
 }
 puts("PASS: EAPOL RX/TX codec; captured descriptor prefix + synthetic body; every truncation, 8 malformed cases, foreign peer, capacity bounds, 20000 malformed frames; no WPA handshake claimed");
 return 0;
}
