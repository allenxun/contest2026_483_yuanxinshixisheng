#include "skw_native.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
int main(void){
 unsigned char s[64]={0};struct skw_packet p;struct skw_hci_packet h;
 s[0]=24;s[3]=5;s[16]=2;s[19]=4; /* logical 12 + H4 + ACL4 + data4 + tail3 */
 assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==0);assert(skw_hci_decode(&p,&h)==0&&h.type==2&&h.length==8);
 s[25]=0xa5;assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==0);assert(skw_hci_decode(&p,&h)==-EPROTO);s[25]=0;
 s[3]=2;assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==0);assert(skw_hci_decode(&p,&h)==-EPROTO);
 s[3]=0x85;assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==-EPROTO);
 s[3]=0xff;assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==0&&p.discard);
 s[3]=5;s[19]=80;assert(skw_sdio2_decode_slot(s,sizeof(s),&p)==0);assert(skw_hci_decode(&p,&h)==-EMSGSIZE);
 puts("PASS actual codec: valid port5 ACL accepted; nonzero pad/wrong H4-port/high channel/short ACL rejected; filler discarded. Synthetic bytes only, no observed failing ACL.");return 0;
}
