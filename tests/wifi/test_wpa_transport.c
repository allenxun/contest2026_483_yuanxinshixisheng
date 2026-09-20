/* SPDX-License-Identifier: GPL-2.0-only */
#include "skw_wpa_transport.h"
#include <assert.h>
#include <stdio.h>
struct mock {
  unsigned calls,fail_call;int failure;
  uint8_t cmd[16],bytes[16][1100];size_t length[16];
};
static int command(void *arg,uint8_t id,const void *data,size_t n)
{
  struct mock *m=arg;unsigned i=m->calls++;
  assert(i<16 && n<=1100);m->cmd[i]=id;m->length[i]=n;
  memcpy(m->bytes[i],data,n);
  return m->calls==m->fail_call ? m->failure:0;
}
static const uint8_t own[6]={2,1,2,3,4,5},ap[6]={2,6,7,8,9,10};
static void wiped(const void *p,size_t n)
{ for(size_t i=0;i<n;i++) assert(!((const uint8_t *)p)[i]); }
static void start(struct skw_wpa_transport *t,struct mock *m)
{
  memset(t,0,sizeof(*t));memset(m,0,sizeof(*m));
  assert(!skw_wpa_begin(t,0,1,7,own,ap,command,m));
}
int main(void)
{
  struct skw_wpa_transport t={0};struct mock m={0};
  uint8_t key[16],rsc[6]={9,8,7,6,5,4},eap[99]={2,3,0,95,2};
  for(unsigned i=0;i<16;i++) key[i]=0xa0+i; /* Synthetic test material only. */
  assert(skw_wpa_send_eapol(&t,eap,99)==-ENOTCONN);
  assert(skw_wpa_begin(&t,1,0,0,own,ap,command,&m)==-EINVAL);
  start(&t,&m);
  assert(skw_wpa_begin(&t,0,1,7,own,ap,command,&m)==-EBUSY);
  assert(!skw_wpa_send_eapol(&t,eap,sizeof(eap)));
  assert(m.calls==1 && m.cmd[0]==15 && m.length[0]==121);
  assert(skw_eap_u16(m.bytes[0])==0x760 && skw_eap_u16(m.bytes[0]+2)==0x1071);
  assert(!memcmp(m.bytes[0]+8,ap,6) && !memcmp(m.bytes[0]+14,own,6));
  assert(!memcmp(m.bytes[0]+22,eap,sizeof(eap)));wiped(t.scratch,sizeof(t.scratch));
  assert(!skw_wpa_install_ccmp(&t,true,0,key,16,rsc,6));
  assert(t.installed==1 && t.attempted==1 && !memcmp(t.initial_rsc[0],rsc,6));
  uint8_t expected[48]={0};memcpy(expected,ap,6);expected[7]=8;expected[8]=1;
  expected[15]=16;memcpy(expected+16,key,16);
  assert(m.cmd[1]==12 && m.length[1]==48 && !memcmp(m.bytes[1],expected,48));
  wiped(t.scratch,sizeof(t.scratch));
  assert(skw_wpa_install_ccmp(&t,true,0,key,16,rsc,6)==-EALREADY && m.calls==2);
  assert(!skw_wpa_install_ccmp(&t,false,2,key,16,NULL,0));
  expected[6]=1;expected[14]=2;
  assert(!memcmp(m.bytes[2],expected,48) && t.installed==9);
  assert(!skw_wpa_clear_keys(&t) && !t.attempted && !t.installed);
  assert(m.calls==5 && m.cmd[3]==13 && m.cmd[4]==13);
  for(unsigned i=3;i<5;i++) {
    assert(m.length[i]==48);wiped(m.bytes[i]+8,6);wiped(m.bytes[i]+15,33);
  }
  wiped(t.initial_rsc,sizeof(t.initial_rsc));wiped(t.scratch,sizeof(t.scratch));
  skw_wpa_closed(&t);wiped(&t,sizeof(t));

  start(&t,&m);
  for(size_t n=0;n<20;n++) if(n!=16)
    assert(skw_wpa_install_ccmp(&t,true,0,key,n,NULL,0)==-EINVAL);
  for(size_t n=1;n<9;n++) if(n!=6)
    assert(skw_wpa_install_ccmp(&t,true,0,key,16,rsc,n)==-EINVAL);
  assert(skw_wpa_install_ccmp(&t,true,1,key,16,NULL,0)==-EINVAL);
  assert(skw_wpa_install_ccmp(&t,false,4,key,16,NULL,0)==-EINVAL);
  assert(skw_wpa_install_ccmp(&t,true,0,key,16,NULL,6)==-EINVAL);
  assert(m.calls==0);
  m.fail_call=1;m.failure=-ETIMEDOUT;
  assert(skw_wpa_install_ccmp(&t,true,0,key,16,rsc,6)==-ETIMEDOUT);
  assert(t.attempted==1 && !t.installed && t.faulted);wiped(t.scratch,sizeof(t.scratch));
  assert(skw_wpa_send_eapol(&t,eap,99)==-EIO && m.calls==1);
  m.fail_call=2;m.failure=-EIO;
  assert(skw_wpa_clear_keys(&t)==-EIO && t.attempted==1);
  assert(skw_wpa_begin(&t,0,1,7,own,ap,command,&m)==-EBUSY);
  assert(!skw_wpa_clear_keys(&t) && !t.attempted);
  assert(t.faulted); /* Clear success alone does not authorize a new session. */
  skw_wpa_closed(&t);wiped(&t,sizeof(t));

  start(&t,&m);
  assert(!skw_wpa_install_ccmp(&t,true,0,key,16,NULL,0));
  assert(!skw_wpa_install_ccmp(&t,false,1,key,16,rsc,6));
  m.fail_call=3;m.failure=-ETIMEDOUT;
  assert(skw_wpa_clear_keys(&t)==-ETIMEDOUT && m.calls==4);
  assert(t.attempted==1 && !t.installed); /* Other delete still attempted. */
  wiped(t.initial_rsc,sizeof(t.initial_rsc));
  skw_wpa_closed(&t);
  start(&t,&m);m.fail_call=1;m.failure=-EIO;
  assert(skw_wpa_send_eapol(&t,eap,99)==-EIO && t.faulted);
  wiped(t.scratch,sizeof(t.scratch));skw_wpa_closed(&t);
  puts("PASS: WPA transport synthetic ACK/fault injection; EAPOL command 15, CCMP 48-byte keys, duplicate-install rejection, uncertain ADD cleanup, delete retry/continue, buffer wipe. No radio/WPA/DHCP success claimed.");
}
