#include "scan_collector.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
  struct sc_collector c, saved;
  struct sc_record r = {0};
  unsigned i;
  sc_init(&c); r.channel=1; r.rssi=-80;
  assert(sc_accept(&c,1,&r)==SC_STALE);
  assert(sc_begin(&c,0)==SC_INVALID);
  assert(sc_begin(&c,1)==SC_OK);
  assert(sc_begin(&c,2)==SC_STATE);
  r.ssid_len=32;
  for(i=0;i<32;i++) r.ssid[i]=(uint8_t)(i*8); /* includes NUL, non-UTF8 */
  assert(sc_accept(&c,1,&r)==SC_OK && c.count==1);
  assert(!memcmp(c.records[0].ssid,r.ssid,32));
  r.rssi=-20; r.security=2; r.channel=149; r.band=1;
  r.ssid_len=3; r.ssid[0]=0; r.ssid[1]=255; r.ssid[2]=10;
  assert(sc_accept(&c,1,&r)==SC_OK && c.count==1);
  assert(c.records[0].security==2 && c.records[0].channel==149 && c.records[0].band==1);
  assert(c.records[0].ssid_len==3 && !memcmp(c.records[0].ssid,r.ssid,3));
  for(i=3;i<32;i++) assert(c.records[0].ssid[i]==0);
  saved=c; r.security=0;
  assert(sc_accept(&c,1,&r)==SC_IGNORED && !memcmp(&c,&saved,sizeof c));
  r.rssi=-21; assert(sc_accept(&c,1,&r)==SC_IGNORED);
  r.ssid_len=33; assert(sc_accept(&c,1,&r)==SC_INVALID);
  r.ssid_len=0; r.security=4; assert(sc_accept(&c,1,&r)==SC_INVALID);
  r.security=0; r.band=2; assert(sc_accept(&c,1,&r)==SC_INVALID);
  r.band=0; r.channel=0; assert(sc_accept(&c,1,&r)==SC_INVALID);
  r.channel=1;
  assert(!memcmp(&c,&saved,sizeof c));
  for(i=1;i<64;i++){r.bssid[5]=(uint8_t)i;assert(sc_accept(&c,1,&r)==SC_OK);}
  assert(c.count==64 && !c.truncated);
  r.bssid[5]=64; assert(sc_accept(&c,1,&r)==SC_FULL && c.truncated && c.count==64);
  r.bssid[5]=63; r.rssi=0; r.security=3;
  assert(sc_accept(&c,1,&r)==SC_OK && c.records[63].security==3);
  saved=c; assert(sc_cancel(&c,2)==SC_STALE && !memcmp(&c,&saved,sizeof c));
  assert(sc_freeze(&c,1)==SC_OK); saved=c;
  assert(sc_accept(&c,1,&r)==SC_STATE && !memcmp(&c,&saved,sizeof c));
  assert(sc_freeze(&c,1)==SC_STATE && sc_cancel(&c,1)==SC_STATE);
  assert(sc_begin(&c,1)==SC_STALE);
  assert(sc_begin(&c,2)==SC_OK && !c.count && !c.truncated);
  saved=c; assert(sc_accept(&c,1,&r)==SC_STALE && !memcmp(&c,&saved,sizeof c));
  assert(sc_accept(&c,2,&r)==SC_OK && sc_cancel(&c,2)==SC_OK);
  assert(c.state==SC_CANCELLED && c.generation==2 && !c.count && !c.truncated);
  { struct sc_record zero[64]={0}; assert(!memcmp(c.records,zero,sizeof zero)); }
  assert(sc_accept(&c,2,&r)==SC_STATE && sc_cancel(&c,2)==SC_STATE);
  assert(sc_begin(&c,UINT64_MAX)==SC_OK && sc_freeze(&c,UINT64_MAX)==SC_OK);
  assert(sc_begin(&c,UINT64_MAX)==SC_STALE && sc_begin(&c,1)==SC_STALE);
  assert(sc_accept(NULL,1,&r)==SC_INVALID && sc_freeze(NULL,1)==SC_INVALID);
  printf("PASS collector: 64/65, full-record replacement, binary SSID, stale/frozen/cancel, overflow; bytes=%zu\n",sizeof c);
  return 0;
}
