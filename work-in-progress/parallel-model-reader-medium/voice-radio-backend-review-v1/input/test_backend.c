#include <pthread.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <time.h>
#include "wifi_scan.h"
#define NXMUTEX_INITIALIZER PTHREAD_MUTEX_INITIALIZER
#define SEM_INITIALIZER(x) {0}
typedef pthread_mutex_t mutex_t;
static int nxmutex_lock(mutex_t*m){return -pthread_mutex_lock(m);}
static int nxmutex_unlock(mutex_t*m){return -pthread_mutex_unlock(m);}
static int nxsem_post(sem_t*s){return sem_post(s);}
static int nxsem_wait_uninterruptible(sem_t*s){int r;do{r=sem_wait(s);}while(r&&errno==EINTR);return r;}
static uint64_t now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
static bool g_wifi_network_active,g_wifi_network_stop,g_bt_worker_fault,g_bt_host_mode=true,g_wifi_info_valid=true;
static mutex_t g_wifi_operation=NXMUTEX_INITIALIZER,g_wifi_state=NXMUTEX_INITIALIZER,g_wifi_ip_state=NXMUTEX_INITIALIZER;
static char g_wifi_target_ssid[33],g_wifi_ip[16];static size_t g_wifi_target_ssid_len;static int g_wifi_ip_result;
static struct {bool active;}g_wifi_wpa;
struct skw_bss {struct{uint8_t ssid[32],ssid_len,bssid[6],channel,band;int rssi;}scan;bool rsn,wpa;unsigned capability;};
static int skw_bss_decode(const void*p,size_t n,struct skw_bss*b){(void)p;(void)n;memset(b,0,sizeof(*b));memcpy(b->scan.ssid,"AP1",3);b->scan.ssid_len=3;b->scan.bssid[0]=2;b->scan.channel=1;b->rsn=true;return 0;}
#include "radio_backend_state.inc"
static int scenario;static bool rx_enabled=true;
static int fw_wifi_info(void){return 0;}
static int fw_wifi_command(uint8_t c,const void*p,size_t n){(void)p;(void)n;int rc=rb_ready&&scenario==1&&c==4?-EIO:rb_ready&&scenario==3&&c==6?-EIO:0;rb_note(c,rc);return rc;}
static int fw_wifi_scan(void){fw_wifi_command(3,NULL,0);fw_wifi_command(5,NULL,0);rb_rx_report(NULL,0);if(scenario==3){fw_wifi_command(6,NULL,0);fw_wifi_command(4,NULL,0);return -ETIMEDOUT;}rb_rx_done();return fw_wifi_command(4,NULL,0);}
static int fw_wifi_join_run(bool x,const char*p){(void)x;(void)p;rb_authenticated(false);rb_keys(0,0);return -EACCES;}
#include "radio_backend.inc"
static void*rx(void*p){(void)p;for(;;){if(__atomic_load_n(&rx_enabled,__ATOMIC_ACQUIRE))rb_rx_idle();usleep(1000);}return NULL;}
#define C(x) do{if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1);}}while(0)
int main(int argc,char**argv){
 C(sem_init(&rb_jobs,0,0)==0);pthread_t t;C(pthread_create(&t,NULL,rx,NULL)==0);C(rb_start()==0);
 scenario=argc>1?atoi(argv[1]):0;if(scenario==2)__atomic_store_n(&rx_enabled,false,__ATOMIC_RELEASE);
 C(k7_wifi_dispatch()!=NULL&&k7_wifi_scans()!=NULL);
 uint64_t id;C(ws_voice_begin(&rb_scan,1000,&id)==WD_OK);struct vs_snapshot v;
 uint64_t end=now_us()+4000000;
 do{C(ws_voice_poll(&rb_scan,id,&v)==WD_OK);if(v.state!=VS_PENDING)break;usleep(1000);}while(now_us()<end);
 if(scenario){C(v.state!=VS_DONE&&v.held);puts("PASS fault scenario remains held; no mock success release");return 0;}
 C(v.state==VS_DONE&&!v.held&&v.count==1);
 C(wd_ble_begin(&rb_dispatch,"AP1",3,"12345678",8,1000,&id)==WD_OK);struct wd_view w;
 end=now_us()+2000000;
 do{C(wd_ble_poll(&rb_dispatch,id,&w)==WD_OK);if(w.status!=WB_RECEIVED&&w.status!=WB_CONNECTING&&!w.held)break;usleep(1000);}while(now_us()<end);
 C(w.status==WB_FAILED&&!w.held);
 puts("PASS real target backend inc + pthread reaper/pump/RX mock; real hardware NOT exercised");return 0;
}
