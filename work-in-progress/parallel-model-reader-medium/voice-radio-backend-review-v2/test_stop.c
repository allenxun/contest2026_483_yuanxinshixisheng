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

static _Thread_local int block_on_unlock;
static bool paused,resume_stop;
static int hooked_unlock(mutex_t*m){int rc=nxmutex_unlock(m);if(block_on_unlock){block_on_unlock=0;__atomic_store_n(&paused,true,__ATOMIC_RELEASE);while(!__atomic_load_n(&resume_stop,__ATOMIC_ACQUIRE))usleep(1000);}return rc;}
#define nxmutex_unlock hooked_unlock
#include "radio_backend_state.inc"

static int scenario;static bool rx_enabled=true;
static int fw_wifi_info(void){return 0;}
static int fw_wifi_command(uint8_t c,const void*p,size_t n){(void)p;(void)n;int rc=rb_ready&&scenario==1&&c==4?-EIO:rb_ready&&scenario==3&&c==6?-EIO:0;rb_note(c,rc);return rc;}
static int fw_wifi_scan(void){fw_wifi_command(3,NULL,0);fw_wifi_command(5,NULL,0);rb_rx_report(NULL,0);if(scenario==3){fw_wifi_command(6,NULL,0);fw_wifi_command(4,NULL,0);return -ETIMEDOUT;}rb_rx_done();return fw_wifi_command(4,NULL,0);}
static int fw_wifi_join_run(bool x,const char*p){(void)x;(void)p;rb_authenticated(false);rb_keys(0,0);return -EACCES;}

#include "radio_backend.inc"
#undef nxmutex_unlock
#define C(x) do{if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1);}}while(0)
static int stop_join(void*p,uint64_t owner,uint64_t id){block_on_unlock=1;return rb_stop(p,owner,id);}
static int stop_scan(void*p,uint64_t id){block_on_unlock=1;return rb_stop_scan(p,id);}
static void*pump_once(void*p){(void)p;C(wd_pump(&rb_dispatch)==WD_OK);return NULL;}
int main(int argc,char**argv){
 (void)&rb_start;(void)&rb_rx_idle;(void)rx_enabled;C(sem_init(&rb_jobs,0,0)==0);rb_enabled=true;
 bool scan=argc>1&&!strcmp(argv[1],"scan");
 struct wd_port dp={NULL,rb_dlock,rb_dunlock,rb_now,rb_submit,stop_join};struct ws_port sp={NULL,rb_submit_scan,stop_scan};
 C(wd_init(&rb_dispatch,&dp,true)==0);C(ws_attach(&rb_scan,&rb_dispatch,&sp)==0);
 uint64_t old,next;
 if(scan)C(ws_voice_begin(&rb_scan,100000,&old)==WD_OK);
 else C(wd_voice_begin(&rb_dispatch,"AP1",3,"12345678",8,100000,&old)==WD_OK);
 C(wd_pump(&rb_dispatch)==WD_OK);uint64_t owner=rb_job.owner,job_id=rb_job.id;
 if(scan)C(ws_voice_cancel(&rb_scan,old)==WD_OK);else C(wd_voice_cancel(&rb_dispatch,old)==WD_OK);
 pthread_t t;C(pthread_create(&t,NULL,pump_once,NULL)==0);
 uint64_t end=now_us()+3000000;while(!__atomic_load_n(&paused,__ATOMIC_ACQUIRE)){C(now_us()<end);usleep(1000);}
 /* Simulated reaper has finished cleanup and owns no worker/RX resources.
  * This is injected test evidence, not proof of real hardware fences. */
 rb_backend_idle();
 if(scan){struct ws_done e={.ticket=old,.sequence=1,.success=true,.scan_done=true,.stop_ok=true,.close_ok=true,.worker_exited=true,.rx_quiescent=true,.offline=true};C(ws_post(&rb_scan,&e)==WD_OK);}
 else{struct wd_event e={0};e.kind=WD_COMPLETION;e.done.owner=owner;e.done.id=job_id;e.done.sequence=1;e.done.worker_exited=1;C(wd_post(&rb_dispatch,&e)==WD_OK);}
 C(wd_ble_begin(&rb_dispatch,"AP2",3,"87654321",8,100000,&next)==WD_OK);
 for(unsigned i=0;i<100;i++)C(wd_pump(&rb_dispatch)==WD_BUSY);
 C(!rb_queued); /* no new submit happened despite pending next command */
 __atomic_store_n(&resume_stop,true,__ATOMIC_RELEASE);C(pthread_join(t,NULL)==0);
 C(__atomic_load_n(&rb_cancelled,__ATOMIC_ACQUIRE)); /* old callback finally wrote */
 C(wd_pump(&rb_dispatch)==WD_OK);
 C(rb_queued&&rb_job.owner==1&&rb_job.id!=0);
 C(!__atomic_load_n(&rb_cancelled,__ATOMIC_ACQUIRE)); /* next enqueue after stop reset */
 struct wd_view view;C(wd_ble_poll(&rb_dispatch,next,&view)==WD_OK&&view.status==WB_CONNECTING);
 /* Exact reset ordering used by fw_wifi_ip_session, tested as a seam only. */
 __atomic_store_n(&g_wifi_network_stop,false,__ATOMIC_RELEASE);
 if(rb_stopping())__atomic_store_n(&g_wifi_network_stop,true,__ATOMIC_RELEASE);
 C(!__atomic_load_n(&g_wifi_network_stop,__ATOMIC_ACQUIRE));
 printf("PASS %s stop paused after match/unlock: 100 competing pumps BUSY; next job starts only after stop return; new cancel=false\n",scan?"scan":"connect");
 return 0;
}
