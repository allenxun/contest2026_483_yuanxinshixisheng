#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
#include "radio_fence.h"
#define CONFIG_EXAMPLES_K7RADIO_IP 1
#define MSEC2TICK(x) (x)
static bool g_wifi_network_active,g_wifi_info_valid=true,g_wifi_calibrated=true,g_bt_host_mode=true,g_wifi_scan_done;
static uint8_t g_wifi_mac[6];static int g_wifi_state,g_wifi_scansem;
static unsigned g_wifi_reports,g_wifi_unique,checks;
static int commands[12],command_count,lock_count,lock_fail,wait_rc,close_rc,scan_rc,stop_rc,open_rc;
#define C(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);exit(1);}}while(0)
static int skw_crc16(int a,const void*b,int c){(void)a;(void)b;(void)c;return 0xd20d;}
static int fw_wifi_command(int cmd,const void*p,size_t n){(void)p;(void)n;commands[command_count++]=cmd;return cmd==3?open_rc:cmd==5?scan_rc:cmd==4?close_rc:cmd==6?stop_rc:0;}
static int nxmutex_lock(int*m){(void)m;return ++lock_count==lock_fail?-EIO:0;}
static int nxmutex_unlock(int*m){(void)m;return 0;}
static int nxsem_trywait(int*s){(void)s;return -1;}
static int nxsem_tickwait_uninterruptible(int*s,int t){(void)s;(void)t;g_wifi_scan_done=!wait_rc;return wait_rc;}
static int fw_receive(int t){(void)t;g_wifi_scan_done=!wait_rc;return wait_rc;}
#include "scan_function.inc"
static void reset(void){command_count=lock_count=lock_fail=wait_rc=close_rc=scan_rc=stop_rc=open_rc=0;g_wifi_scan_done=false;memset(commands,0,sizeof(commands));}
int main(void){
 reset();C(fw_wifi_scan()==0);C(command_count==3&&commands[0]==3&&commands[1]==5&&commands[2]==4);
 reset();lock_fail=1;C(fw_wifi_scan()==-EIO);C(command_count==2&&commands[0]==3&&commands[1]==4);
 reset();wait_rc=-ETIMEDOUT;C(fw_wifi_scan()==-ETIMEDOUT);C(command_count==4&&commands[2]==6&&commands[3]==4);
 reset();close_rc=-EIO;C(fw_wifi_scan()==-EIO);C(commands[command_count-1]==4);
 reset();scan_rc=-EIO;stop_rc=-ETIMEDOUT;C(fw_wifi_scan()==-EIO);C(commands[2]==6&&commands[3]==4);
 struct rf_facts f;rf_init(&f);C(!rf_scan_releasable(&f));f.worker_joined=true;C(rf_scan_releasable(&f));
 rf_command(&f,3,-ETIMEDOUT,1);C(!rf_scan_releasable(&f));rf_command(&f,6,0,2);rf_command(&f,4,0,3);
 f.rx_empty=f.callbacks_exited=true;f.empty_epoch=4;C(rf_scan_releasable(&f));
 C(rf_scan_releasable(&f));f.empty_epoch=3;C(!rf_scan_releasable(&f));
 f.empty_epoch=4;f.maintenance_joined=f.keys_clean=f.unjoined=true;C(rf_connect_releasable(&f));
 f.keys_clean=false;C(!rf_connect_releasable(&f));
 printf("PASS %u checks real frozen fw_wifi_scan with mocked commands/locks only; no radio acceptance\n",checks);
}
