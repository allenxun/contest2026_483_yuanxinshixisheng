from pathlib import Path
p=Path(__file__).parent
s=(p/'candidate/k7radio_main.c').read_text()
send=s[s.index('static int bt_lower_send('):s.index('static const struct skw_bt_lower g_bt_lower')]
worker=s[s.index('static int bt_tx_worker('):s.index('static int bt_rx_worker(')]
prefix=r'''#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "bt_meta.h"
#define SKW_BT_DATA_PORT 5
#define MSEC2TICK(n) (n)
struct bt_meta g_bt_meta;
struct radio_bt_tx { uint8_t data[2048]; size_t length; };
static struct radio_bt_tx g_bt_queue[8],g_bt_current;
static int g_bt_qlock,g_bt_items,g_bt_acksem;
static unsigned g_bt_head,g_bt_tail,g_bt_count,g_bt_host_tx,g_bt_host_ack;
static bool g_bt_pending,g_bt_worker_fault;
static uint8_t g_bt_pending_channel;
static int sent_result,wait_result,match_ack,wait_calls,lock_result;
static int nxmutex_lock(int *p){(void)p;return lock_result;}
static void nxmutex_unlock(int *p){(void)p;}
static int nxsem_post(int *p){(void)p;return 0;}
static int nxsem_trywait(int *p){(void)p;return -EAGAIN;}
static int nxsem_wait_uninterruptible(int *p){(void)p;return wait_calls++?-EINTR:0;}
static int nxsem_tickwait_uninterruptible(int *p,int n){(void)p;(void)n;return wait_result;}
static int bt_lower_ack(void *,uint8_t,uint16_t);
static int fw_packet(bool w,void *p,size_t n){(void)w;(void)p;(void)n;if(match_ack)bt_lower_ack(0,5,0);return sent_result;}
'''
tail=r'''
static void reset(void){memset(&g_bt_meta,0,sizeof(g_bt_meta));g_bt_head=g_bt_tail=g_bt_count=0;g_bt_pending=false;g_bt_worker_fault=false;sent_result=wait_result=match_ack=wait_calls=lock_result=0;}
static void queue(void){uint8_t b[4]={0,0,0,5};assert(!bt_lower_send(0,b,4));assert(bm_get(BM_ACL_QUEUED)==1);}
int main(void){
 reset();queue();sent_result=-EIO;assert(bt_tx_worker(0,0)==-EIO);assert(bm_get(BM_ACL_SEND_FAIL)==1);assert(!bm_get(BM_ACL_SEND_OK));assert(!bm_get(BM_ACL_ACK_MATCH));
 reset();queue();match_ack=1;assert(bt_tx_worker(0,0)==-EINTR);assert(bm_get(BM_ACL_SEND_OK)==1&&bm_get(BM_ACL_ACK_MATCH)==1);
 assert(!bt_lower_ack(0,5,0));assert(bm_get(BM_ACL_ACK_OTHER)==1);
 reset();queue();wait_result=-ETIMEDOUT;assert(bt_tx_worker(0,0)==-ETIMEDOUT);assert(bm_get(BM_ACL_ACK_WAIT_FAIL)==1&&g_bt_meta.last_wait_error==-ETIMEDOUT);
 reset();g_bt_count=8;uint8_t b[4]={0,0,0,5};assert(bt_lower_send(0,b,4)==-EAGAIN);assert(!bm_get(BM_ACL_QUEUED));
 reset();lock_result=-EBUSY;assert(bt_lower_send(0,b,4)==-EBUSY);assert(!bm_get(BM_ACL_QUEUED));
 puts("PASS extracted actual queue/worker/ACK functions: send failure, ACK match/unmatched, timeout, queue full, lock failure");return 0;
}
'''
status=s[s.index('static int fw_ble_status(void)'):s.index('int main(int argc, char **argv)')]
extra='static bool g_bt_host_mode=true;\nstatic struct { int lock; unsigned connected,handle,acl_rx,acl_tx,connections,disconnections,disconnect_reason,encryption_status,encryption_enabled; } g_native_bt;\n'
tail=tail.replace('puts("PASS extracted', 'lock_result=0;assert(!fw_ble_status());assert(!bm_get(BM_ACL_QUEUED));puts("PASS extracted')
(p/'test_tx.c').write_text(prefix+extra+send+worker+status+tail)
