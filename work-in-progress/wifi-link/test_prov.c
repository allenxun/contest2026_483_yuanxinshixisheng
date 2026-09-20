/* SPDX-License-Identifier: Apache-2.0 */
#include "prov_protocol.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
 prov_protocol_init();struct prov_rx rx={0};struct prov_request req;
 const char *valid="{\"v\":1,\"id\":42,\"cmd\":\"status\"}\n";
 for(size_t step=1;step<=20;step++)
  { prov_rx_reset(&rx);size_t n=strlen(valid);
    for(size_t i=0;i<n;i+=step) {size_t m=n-i<step?n-i:step;assert(prov_rx_feed(&rx,valid+i,m,100)==(i+m==n));}
    assert(!prov_parse(rx.data,&req) && req.command==PROV_STATUS && req.id==42);
  }
 prov_rx_reset(&rx);assert(prov_rx_feed(&rx,"X",1,0)==1);assert(!prov_parse(rx.data,&req) && req.command==PROV_SCAN);
 prov_rx_reset(&rx);assert(!prov_rx_feed(&rx,"{",1,0));assert(prov_rx_feed(&rx,"}",1,10000)==-ETIMEDOUT && !rx.used);
 assert(prov_rx_feed(&rx,"a\nb",3,0)==-EPROTO && !rx.used);
 assert(prov_rx_feed(&rx,"a\0b",3,0)==-EPROTO && !rx.used);
 const char block[]="aaaaaaaaaaaaaaaaaaaa";
 for(int i=0;i<25;i++)assert(!prov_rx_feed(&rx,block,20,1));
 assert(prov_rx_feed(&rx,block,20,1)==-EMSGSIZE && !rx.used && rx.discard);
 assert(prov_rx_feed(&rx,"X",1,1)==-EMSGSIZE);
 assert(prov_rx_feed(&rx,"\n",1,1)==-EMSGSIZE && !rx.discard);
 assert(prov_parse("{\"v\":1,\"id\":2,\"id\":3,\"cmd\":\"scan\"}",&req));
 assert(prov_parse("{\"v\":1,\"id\":2.5,\"cmd\":\"scan\"}",&req));
 assert(prov_parse("{\"v\":2,\"id\":2,\"cmd\":\"scan\"}",&req));
 assert(prov_parse("{\"v\":1,\"id\":2,\"cmd\":\"scan\\u0000evil\"}",&req));
 assert(prov_parse("[[[[[[[[[[0]]]]]]]]]]",&req));
 assert(prov_parse("{\"v\":1,\"id\":3,\"cmd\":\"connect\",\"password\":\"synthetic-test-only\"}",&req));
 assert(!prov_parse("{\"v\":1,\"id\":3,\"cmd\":\"connect\",\"ssid_b64\":\"TGFuc2Vl\",\"password\":\"synthetic-test-only\"}",&req) && req.command==PROV_CONNECT && req.ssid_len==6);
 assert(prov_parse("{\"v\":1,\"id\":4,\"cmd\":\"connect\",\"ssid_b64\":\"TGFuc2Vl\",\"password\":\"short\"}",&req));
 for(size_t i=0;i<sizeof(req.password);i++)assert(!req.password[i]);
 char encoded[45];prov_base64((const uint8_t *)"Lansee",6,encoded);assert(!strcmp(encoded,"TGFuc2Vl"));
 unsigned int seed=31;
 for(int j=0;j<20000;j++)
  { char malformed[100];for(size_t i=0;i<99;i++){seed=seed*1664525u+1013904223u;malformed[i]=(char)((seed>>24)|1);}malformed[99]=0;
    (void)prov_parse(malformed,&req);prov_rx_reset(&rx);(void)prov_rx_feed(&rx,malformed,(j%20)+1,(uint32_t)j);
  }
 prov_rx_reset(&rx);for(size_t i=0;i<sizeof(rx);i++)assert(!((unsigned char *)&rx)[i]);
 puts("PASS: 1..20 byte fragmentation, full input wiping, timeout, overflow discard, duplicate/invalid JSON, bounded nesting, 20000 malformed requests");
 return 0;
}
