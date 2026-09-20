/* SPDX-License-Identifier: Apache-2.0 */
#include "includes.h"
#include "common.h"
#include "common/wpa_common.h"
#include "crypto/sha1.h"
#include "crypto/aes_wrap.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "skw_supplicant.h"
static const uint8_t own[]={2,0,0,0,0,1},ap[]={2,0,0,0,0,2};
static const uint8_t rsn[]={48,20,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,2,0,0};
static uint8_t transmitted[1100],ptk_key[16],gtk_key[16];
static size_t transmitted_len;
static unsigned tx_count,install_count;
static int fail_command;
static int command(void *arg,uint8_t id,const void *p,size_t n)
{
  (void)arg;const uint8_t *data=p;if(fail_command==id)return -ETIMEDOUT;
  if(id==15){assert(n>=22 && n-22<=sizeof(transmitted));memcpy(transmitted,data+22,n-22);transmitted_len=n-22;tx_count++;}
  else if(id==12){assert(n==48 && data[15]==16);memcpy(data[6]?gtk_key:ptk_key,data+16,16);install_count++;}
  return 0;
}
static int random_test(uint8_t *p,size_t n)
{for(size_t i=0;i<n;i++)p[i]=(uint8_t)(i+17);return 0;} /* Test fixture only. */
int main(void)
{
  setbuf(stdout,NULL);
  struct skw_wpa_transport t={0};uint8_t ie[128];size_t n=sizeof(ie);
  assert(!skw_wpa_begin(&t,0,0,1,own,ap,command,NULL));
  struct skw_supplicant *s=skw_supplicant_start(&t,(const uint8_t *)"IEEE",4,"password",rsn,sizeof(rsn),random_test);
  assert(s);assert(!skw_supplicant_assoc_ie(s,ie,&n));assert(n>=22);
  skw_supplicant_associated(s);assert(!skw_supplicant_completed(s));
  uint8_t m1[99]={2,3,0,95,2};
  WPA_PUT_BE16(m1+5,0x008a);WPA_PUT_BE16(m1+7,16);m1[16]=1;
  for(unsigned i=0;i<32;i++)m1[17+i]=(uint8_t)(i+81);
  assert(!skw_supplicant_receive(s,m1,sizeof(m1)));
  assert(tx_count==1 && transmitted_len>=121 && !install_count);
  uint8_t pmk[32],mic[20],saved_mic[16];struct wpa_ptk ptk={0};
  static const uint8_t expected_pmk[]={0xf4,0x2c,0x6f,0xc5,0x2d,0xf0,0xeb,0xef,0x9e,0xbb,0x4b,0x90,0xb3,0x8a,0x5f,0x90,0x2e,0x83,0xfe,0x1b,0x13,0x5a,0x70,0xe2,0x3a,0xed,0x76,0x2e,0x97,0x10,0xa1,0x2e};
  assert(!pbkdf2_sha1("password",(const uint8_t *)"IEEE",4,4096,pmk,32));
  assert(!memcmp(pmk,expected_pmk,32));
  assert(!wpa_pmk_to_ptk(pmk,32,"Pairwise key expansion",own,ap,
    transmitted+17,m1+17,&ptk,WPA_KEY_MGMT_PSK,WPA_CIPHER_CCMP,NULL,0,0));
  memcpy(saved_mic,transmitted+81,16);memset(transmitted+81,0,16);
  assert(!hmac_sha1(ptk.kck,16,transmitted,transmitted_len,mic));
  assert(!memcmp(saved_mic,mic,16));
  uint8_t key_data[48]={0},m3[155]={2,3,0,151,2};
  memcpy(key_data,rsn,22);key_data[22]=221;key_data[23]=22;
  key_data[24]=0;key_data[25]=15;key_data[26]=172;key_data[27]=1;key_data[28]=1;
  for(unsigned i=0;i<16;i++)key_data[30+i]=(uint8_t)(i+160);
  key_data[46]=221;
  WPA_PUT_BE16(m3+5,0x13ca);WPA_PUT_BE16(m3+7,16);m3[16]=2;
  memcpy(m3+17,m1+17,32);WPA_PUT_BE16(m3+97,56);
  assert(!aes_wrap(ptk.kek,16,6,key_data,m3+99));
  assert(!hmac_sha1(ptk.kck,16,m3,sizeof(m3),mic));memcpy(m3+81,mic,16);
  /* Invalid MIC must not install a key or report success. */
  m3[81]^=1;skw_supplicant_receive(s,m3,sizeof(m3));
  assert(!install_count && !skw_supplicant_completed(s));m3[81]^=1;
  assert(!skw_supplicant_receive(s,m3,sizeof(m3)));
  assert(skw_supplicant_completed(s) && install_count==2 && tx_count==2);
  assert(!memcmp(ptk_key,ptk.tk,16) && !memcmp(gtk_key,key_data+30,16));
  /* Retransmitted message 3 with a fresh replay counter must ACK without reinstall. */
  m3[16]=3;memset(m3+81,0,16);assert(!hmac_sha1(ptk.kck,16,m3,sizeof(m3),mic));memcpy(m3+81,mic,16);
  assert(!skw_supplicant_receive(s,m3,sizeof(m3)));
  assert(install_count==2 && tx_count==3 && skw_supplicant_completed(s));
  /* Older replay counter is discarded without a response. */
  m3[16]=2;memset(m3+81,0,16);assert(!hmac_sha1(ptk.kck,16,m3,sizeof(m3),mic));memcpy(m3+81,mic,16);
  skw_supplicant_receive(s,m3,sizeof(m3));assert(tx_count==3 && install_count==2);
  skw_supplicant_stop(s);assert(!skw_wpa_clear_keys(&t));skw_wpa_closed(&t);
  puts("PASS: upstream WPA2 handshake, known PMK, M2 MIC, PTK/GTK, bad MIC, replay and no key reinstall");return 0;
}
