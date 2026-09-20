/* SPDX-License-Identifier: Apache-2.0 */
#include "prov_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void parse(const char *ssid,const char *password,int ok,enum prov_input_error error)
{
 char json[513];struct prov_request r;
 snprintf(json,sizeof(json),"{\"v\":1,\"id\":321,\"cmd\":\"submit_credentials\",\"ssid_b64\":\"%s\",\"password\":\"%s\"}",ssid,password);
 int ret=prov_parse(json,&r);assert((ret==0)==ok);assert(r.id==321 && r.command==PROV_CREDENTIALS);
 if(!ok) { assert(r.error==error);for(size_t i=0;i<sizeof(r.password);i++) assert(!r.password[i]);assert(!r.ssid_len); }
 else assert(r.ssid_len>=1 && r.ssid_len<=32);
 prov_zero(&r,sizeof(r));
}
int main(void)
{
 prov_protocol_init();
 parse("TGFuc2Vl","EXAMPLE_123",1,0);
 parse("YQ==","12345678",1,0);
 parse("YR==","12345678",0,PROV_INVALID_SSID); /* noncanonical unused bits */
 parse("YQ=","12345678",0,PROV_INVALID_SSID);
 parse("","12345678",0,PROV_INVALID_SSID);
 parse("!!!!","12345678",0,PROV_INVALID_SSID);
 parse("TGFuc2Vl","1234567",0,PROV_INVALID_PASSWORD);
 parse("TGFuc2Vl","1234567\\n",0,PROV_INVALID_PASSWORD);
 parse("TGFuc2Vl","1234567\\u4e2d",0,PROV_INVALID_PASSWORD);
 char pass[65];memset(pass,'x',64);pass[64]=0;
 parse("TGFuc2Vl",pass,0,PROV_INVALID_PASSWORD);pass[63]=0;parse("TGFuc2Vl",pass,1,0);
 uint8_t bytes[33];memset(bytes,0xff,sizeof(bytes));char b64[49];
 prov_base64(bytes,32,b64);parse(b64,"12345678",1,0);
 prov_base64(bytes,33,b64);parse(b64,"12345678",0,PROV_INVALID_SSID);
 const char *json="{\"v\":1,\"id\":77,\"cmd\":\"submit_credentials\",\"ssid_b64\":\"TGFuc2Vl\",\"password\":\" space\\\\quote\\\" \"}\n";
 for(size_t width=1;width<=20;width++) {
   struct prov_rx rx={0};struct prov_request r;
   size_t n=strlen(json);
   for(size_t pos=0;pos<n;pos+=width) {
     size_t count=n-pos<width?n-pos:width;
     assert(prov_rx_feed(&rx,json+pos,count,100)==(pos+count==n?1:0));
   }
   assert(!prov_parse(rx.data,&r));assert(!strcmp(r.password," space\\quote\" "));
   assert(r.id==77 && r.ssid_len==6 && !memcmp(r.ssid,"Lansee",6));
   prov_zero(&r,sizeof(r));prov_rx_reset(&rx);
   for(size_t i=0;i<sizeof(rx);i++) assert(!((uint8_t *)&rx)[i]);
 }
 struct prov_request r;
 assert(!prov_parse("{\"v\":1,\"id\":1,\"cmd\":\"connect\"}",&r) && r.command==PROV_CONNECT);
 puts("PASS: credentials reception parser; SSID canonical Base64 1..32 bytes; ASCII password 8..63; invalid input wiped; every BLE chunk width; spaces, slash and quote preserved; no Wi-Fi connection attempted.");
}
