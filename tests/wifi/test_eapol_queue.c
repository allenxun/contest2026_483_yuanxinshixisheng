/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_eapol_queue.h"
#include <assert.h>
#include <stdio.h>
/* Synthetic descriptor and key body. No captured handshake or MIC validation. */
static void fixture(uint8_t f[135],const uint8_t own[6],const uint8_t ap[6])
{
  memset(f,0,135);skw_eap_put16(f,131);f[3]=7;f[4]=4;
  skw_eap_put16(f+10,0x204);skw_eap_put16(f+16,107);f[18]=74;
  memcpy(f+22,own,6);memcpy(f+28,ap,6);f[34]=0x88;f[35]=0x8e;
  f[36]=2;f[37]=3;f[39]=95;f[40]=2;
}
int main(void)
{
  struct skw_eapol_queue q={0};struct skw_eapol_packet out;
  uint8_t own[6]={2,1,2,3,4,5},ap[6]={2,6,7,8,9,10},f[135];
  fixture(f,own,ap);
  assert(skw_eapol_push(&q,f,sizeof(f))==-ENOTCONN);
  assert(!skw_eapol_begin(&q,true,0,0,own,ap));
  for (unsigned i=0;i<4;i++) { f[41]=i;assert(!skw_eapol_push(&q,f,sizeof(f))); }
  assert(skw_eapol_push(&q,f,sizeof(f))==-ENOSPC && q.overflow==1);
  memset(f,0,sizeof(f)); /* Shared FIFO reused: queued copies must survive. */
  for (unsigned i=0;i<2;i++) { assert(!skw_eapol_pop(&q,&out));assert(out.length==99 && out.data[5]==i); }
  fixture(f,own,ap);
  for (unsigned i=4;i<6;i++) { f[41]=i;assert(!skw_eapol_push(&q,f,sizeof(f))); }
  for (unsigned i=2;i<6;i++) { assert(!skw_eapol_pop(&q,&out));assert(out.data[5]==i); }
  assert(skw_eapol_pop(&q,&out)==-EAGAIN && out.length==0);
  for (size_t n=0;n<sizeof(q.packets);n++) assert(!((uint8_t *)q.packets)[n]);
  for (size_t n=0;n<sizeof(f);n++) assert(skw_eapol_push(&q,f,n)<0);
  f[28]^=1;assert(skw_eapol_push(&q,f,sizeof(f))==-EACCES);f[28]^=1;
  assert(!skw_eapol_push(&q,f,sizeof(f)));
  skw_eapol_clear(&q);
  for (size_t n=0;n<sizeof(q);n++) assert(!((uint8_t *)&q)[n]);
  assert(skw_eapol_pop(&q,&out)==-ENOTCONN);
  assert(!skw_eapol_begin(&q,true,0,1,own,ap));
  assert(skw_eapol_push(&q,f,sizeof(f))==-EACCES); /* Previous peer rejected. */
  assert(skw_eapol_begin(&q,true,4,0,own,ap)==-EINVAL && !q.active);
  puts("PASS: EAPOL copied RX queue; capacity, FIFO wrap, slot reuse, all truncations, peer binding, disconnect wipe; synthetic only");
}
