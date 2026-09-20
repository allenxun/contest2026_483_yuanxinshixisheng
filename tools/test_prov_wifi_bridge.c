/* Host regression test of the actual provisioning bridge, with fake clock,
 * mutexes and radio backend. This is not hardware acceptance. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include "prov_protocol.h"
#define CONFIG_EXAMPLES_K7RADIO_IP 1
static int g_wifi_ip_state,g_wifi_operation,g_wifi_state,g_wifi_ip_result;
static bool g_wifi_network_active,g_wifi_network_stop,locked,stuck;
static char g_wifi_ip[16];
static uint8_t g_wifi_target_ssid[32];static size_t g_wifi_target_ssid_len;
static uint64_t clock_us;static unsigned joins;static int join_result;
static uint8_t observed_ssid[32];static size_t observed_len;
static int nxmutex_lock(int *m){(void)m;return 0;}
static int nxmutex_unlock(int *m){if(m==&g_wifi_operation)locked=false;return 0;}
static int nxmutex_trylock(int *m){assert(m==&g_wifi_operation);if(locked)return -EBUSY;locked=true;return 0;}
static uint64_t now_us(void){return clock_us;}
static void fake_sleep(unsigned usec){clock_us+=usec;if(g_wifi_network_stop && !stuck)g_wifi_network_active=false;}
#define usleep fake_sleep
static int fw_wifi_join_run(bool associate,const char *password)
{
 assert(associate && !strcmp(password,"TEST_ONLY_123"));
 assert(!g_wifi_network_active);joins++;
 observed_len=g_wifi_target_ssid_len;memcpy(observed_ssid,g_wifi_target_ssid,observed_len);
 g_wifi_network_active=!join_result;g_wifi_ip_result=join_result;
 strcpy(g_wifi_ip,join_result?"":"10.3.0.214");return join_result;
}
#include "prov_wifi.inc"
int main(void)
{
 struct prov_request r={.ssid={0x41,0,0xe4,0xb8,0xad},.ssid_len=5,.password="TEST_ONLY_123"};
 char ip[16];assert(!prov_wifi_snapshot(ip) && !ip[0]);
 assert(!prov_wifi_connect(&r));assert(joins==1 && observed_len==5 && !memcmp(observed_ssid,r.ssid,5));
 assert(g_wifi_target_ssid_len==6 && !memcmp(g_wifi_target_ssid,"Lansee",6));
 assert(prov_wifi_snapshot(ip) && !strcmp(ip,"10.3.0.214"));
 locked=true;assert(prov_wifi_connect(&r)==-EBUSY && joins==1 && !g_wifi_network_stop);locked=false;
 stuck=true;assert(prov_wifi_connect(&r)==-EBUSY && joins==1 && !locked);stuck=false;
 join_result=-ETIMEDOUT;assert(prov_wifi_connect(&r)==-ETIMEDOUT && joins==2 && !locked);
 assert(!prov_wifi_snapshot(ip) && !ip[0]);
 assert(!strcmp(prov_wifi_error(-ETIMEDOUT),"connection_timeout"));
 assert(!strcmp(prov_wifi_error(-ENOENT),"network_not_found"));
 assert(!strcmp(prov_wifi_error(-ENOTSUP),"unsupported_security"));
 assert(!strcmp(prov_wifi_error(-EIO),"connection_failed"));
 puts("PASS: exact binary SSID, real IP snapshot, operation contention, bounded stop, failure propagation and selector restoration");
}
