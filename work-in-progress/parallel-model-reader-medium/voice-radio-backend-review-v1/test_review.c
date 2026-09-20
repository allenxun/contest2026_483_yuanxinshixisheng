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
#ifdef ORIGINAL
#include "input/radio_backend_state.inc"
#else
#include "radio_backend_state.inc"
#endif
static bool worker_go=true,join_failure;
static unsigned intercepted;
static int next_state=-1;

static int scenario;static bool rx_enabled=true;
static int fw_wifi_info(void){return 0;}
static int fw_wifi_command(uint8_t c,const void*p,size_t n){(void)p;(void)n;int rc=rb_ready&&scenario==1&&c==4?-EIO:rb_ready&&scenario==3&&c==6?-EIO:0;rb_note(c,rc);return rc;}
static int fw_wifi_scan(void){while(!__atomic_load_n(&worker_go,__ATOMIC_ACQUIRE))usleep(1000);fw_wifi_command(3,NULL,0);fw_wifi_command(5,NULL,0);rb_rx_report(NULL,0);if(scenario==3){fw_wifi_command(6,NULL,0);fw_wifi_command(4,NULL,0);return -ETIMEDOUT;}rb_rx_done();return fw_wifi_command(4,NULL,0);}
static int fw_wifi_join_run(bool x,const char*p){(void)x;(void)p;rb_authenticated(false);rb_keys(0,0);return -EACCES;}

static int join_hook(pthread_t t,void**r){if(join_failure)return EINVAL;return pthread_join(t,r);}
static enum wd_rc post_hook(struct ws_service*,const struct ws_done*);
#define pthread_join join_hook
#define ws_post post_hook
#ifdef ORIGINAL
#include "input/radio_backend.inc"
#else
#include "radio_backend.inc"
#endif
#undef ws_post
#undef pthread_join
#define C(x) do{if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1);}}while(0)
static enum wd_rc post_hook(struct ws_service*s,const struct ws_done*e){
 enum wd_rc rc=ws_post(s,e);
 if(rc==WD_OK&&!intercepted){
  intercepted=1;C(wd_pump(&rb_dispatch)==WD_OK);uint64_t next;C(ws_voice_begin(s,100000,&next)==WD_OK);C(wd_pump(&rb_dispatch)==WD_OK);
  struct vs_snapshot v;C(ws_voice_poll(s,next,&v)==WD_OK);next_state=v.state;
#ifdef ORIGINAL
  C(v.state==VS_FAILED);
#else
  C(v.state==VS_PENDING&&v.held);
#endif
  __atomic_store_n(&intercepted,2,__ATOMIC_RELEASE);
 }
 return rc;
}
static void*rx(void*p){(void)p;for(;;){if(__atomic_load_n(&rx_enabled,__ATOMIC_ACQUIRE))rb_rx_idle();usleep(1000);}return NULL;}
int main(int argc,char**argv){
 (void)&rb_start;C(sem_init(&rb_jobs,0,0)==0);rb_enabled=true;
 struct wd_port dp={NULL,rb_dlock,rb_dunlock,rb_now,rb_submit,rb_stop};struct ws_port sp={NULL,rb_submit_scan,rb_stop_scan};
 C(wd_init(&rb_dispatch,&dp,true)==0);C(ws_attach(&rb_scan,&rb_dispatch,&sp)==0);
 if(argc>1&&!strcmp(argv[1],"join")){join_failure=true;worker_go=false;rb_result=31337;}
 pthread_t reaper,rxt;C(pthread_create(&rxt,NULL,rx,NULL)==0);C(pthread_create(&reaper,NULL,rb_reaper,NULL)==0);
 uint64_t id;C(ws_voice_begin(&rb_scan,100000,&id)==WD_OK);C(wd_pump(&rb_dispatch)==WD_OK);
 uint64_t end=now_us()+3000000;
 if(join_failure){
  for(;;){nxmutex_lock(&rb_lock);
#ifdef ORIGINAL
   bool observed=rb_result==-EINVAL;
#else
   bool observed=rb_join_error==-EINVAL;C(rb_result==31337);
#endif
   nxmutex_unlock(&rb_lock);if(observed)break;C(now_us()<end);usleep(1000);}
  puts("PASS deterministic live-worker join-error ownership check");
  __atomic_store_n(&worker_go,true,__ATOMIC_RELEASE);return 0;
 }
 while(__atomic_load_n(&intercepted,__ATOMIC_ACQUIRE)!=2){C(now_us()<end);usleep(1000);}
 printf("PASS terminal queue interleave next_state=%d (original FAILED=4; fixed PENDING=0)\n",next_state);return 0;
}
