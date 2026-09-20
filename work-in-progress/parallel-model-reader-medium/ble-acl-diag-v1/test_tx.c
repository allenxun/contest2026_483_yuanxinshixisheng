#include <assert.h>
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
static bool g_bt_host_mode=true;
static struct { int lock; unsigned connected,handle,acl_rx,acl_tx,connections,disconnections,disconnect_reason,encryption_status,encryption_enabled; } g_native_bt;
static int bt_lower_send(void *ctx, const void *packet, size_t length)
{
  int ret;
  (void)ctx;
  if (!packet || !length || length > sizeof(g_bt_queue[0].data)) return -EMSGSIZE;
  ret = nxmutex_lock(&g_bt_qlock);
  if (ret) return ret;
  if (g_bt_count == 8 || __atomic_load_n(&g_bt_worker_fault, __ATOMIC_ACQUIRE))
    { nxmutex_unlock(&g_bt_qlock); return -EAGAIN; }
  memcpy(g_bt_queue[g_bt_tail].data, packet, length);
  g_bt_queue[g_bt_tail].length = length;
  g_bt_tail = (g_bt_tail + 1) % 8; g_bt_count++;
  if (length >= 4 && ((const uint8_t *)packet)[3] == SKW_BT_DATA_PORT) bm_inc(BM_ACL_QUEUED);
  nxmutex_unlock(&g_bt_qlock);
  nxsem_post(&g_bt_items);
  return 0;
}
static int bt_lower_ack(void *ctx, uint8_t channel, uint16_t seq)
{
  bool pending = true;
  (void)ctx; (void)seq;
  if (channel == __atomic_load_n(&g_bt_pending_channel, __ATOMIC_ACQUIRE) &&
      __atomic_compare_exchange_n(&g_bt_pending, &pending, false, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE))
    {
      __atomic_add_fetch(&g_bt_host_ack, 1, __ATOMIC_RELAXED);
      if (channel == SKW_BT_DATA_PORT) bm_inc(BM_ACL_ACK_MATCH);
      nxsem_post(&g_bt_acksem);
    }
  else if (channel == SKW_BT_DATA_PORT) bm_inc(BM_ACL_ACK_OTHER);
  return 0;
}
static int bt_tx_worker(int argc, char **argv)
{
  int ret = 0;
  (void)argc; (void)argv;
  while (!__atomic_load_n(&g_bt_worker_fault, __ATOMIC_ACQUIRE))
    {
      ret = nxsem_wait_uninterruptible(&g_bt_items);
      if (ret) break;
      if (__atomic_load_n(&g_bt_worker_fault, __ATOMIC_ACQUIRE)) break;
      if ((ret = nxmutex_lock(&g_bt_qlock))) break;
      if (!g_bt_count) { nxmutex_unlock(&g_bt_qlock); continue; }
      memcpy(&g_bt_current, &g_bt_queue[g_bt_head], sizeof(g_bt_current));
      g_bt_head = (g_bt_head + 1) % 8; g_bt_count--;
      nxmutex_unlock(&g_bt_qlock);
      while (nxsem_trywait(&g_bt_acksem) == 0) {}
      __atomic_store_n(&g_bt_pending_channel, g_bt_current.data[3], __ATOMIC_RELEASE);
      __atomic_store_n(&g_bt_pending, true, __ATOMIC_RELEASE);
      ret = fw_packet(true, g_bt_current.data, g_bt_current.length);
      bm_send(g_bt_current.data[3], ret);
      if (ret) break;
      __atomic_add_fetch(&g_bt_host_tx, 1, __ATOMIC_RELAXED);
      ret = nxsem_tickwait_uninterruptible(&g_bt_acksem, MSEC2TICK(1500));
      if (ret && g_bt_current.data[3] == SKW_BT_DATA_PORT)
        { bm_inc(BM_ACL_ACK_WAIT_FAIL); bm_error(&g_bt_meta.last_wait_error, ret); }
      if (ret) break;
    }
  __atomic_store_n(&g_bt_worker_fault, true, __ATOMIC_RELEASE);
  printf("RADIO BT TX worker stopped ret=%d\n", ret);
  return ret;
}
static int fw_ble_status(void)
{
  if(!g_bt_host_mode) return -ENODEV;
  int ret=nxmutex_lock(&g_native_bt.lock);
  if(ret) return ret;
  printf("RADIO BLE name=VelaVision K7 connected=%u handle=%u ACL_RX=%u ACL_TX_queued=%u\n",
    g_native_bt.connected,g_native_bt.handle,g_native_bt.acl_rx,g_native_bt.acl_tx);
  printf("RADIO BLE history connections=%u disconnections=%u last_reason=%u encrypt_status=%u encrypted=%u\n",
    g_native_bt.connections,g_native_bt.disconnections,g_native_bt.disconnect_reason,
    g_native_bt.encryption_status,g_native_bt.encryption_enabled);
  nxmutex_unlock(&g_native_bt.lock);
  /* Relaxed atomic reads: each field valid; this is not a coherent snapshot. */
  printf("RADIO BTM ACL_QUEUED=%u ACL_SEND_OK=%u ACL_SEND_FAIL=%u ACL_ACK_MATCH=%u\n",
    (unsigned)bm_get(BM_ACL_QUEUED),(unsigned)bm_get(BM_ACL_SEND_OK),(unsigned)bm_get(BM_ACL_SEND_FAIL),(unsigned)bm_get(BM_ACL_ACK_MATCH));
  printf("RADIO BTM ACL_ACK_OTHER=%u ACL_ACK_WAIT_FAIL=%u PORT5_SLOT=%u SLOT_DECODE_FAIL=%u\n",
    (unsigned)bm_get(BM_ACL_ACK_OTHER),(unsigned)bm_get(BM_ACL_ACK_WAIT_FAIL),(unsigned)bm_get(BM_PORT5_SLOT),(unsigned)bm_get(BM_SLOT_DECODE_FAIL));
  printf("RADIO BTM PORT5_SLOT_DECODE_FAIL=%u HCI_DECODE_FAIL=%u PORT5_HCI_DECODE_FAIL=%u READY_REJECT=%u\n",
    (unsigned)bm_get(BM_PORT5_SLOT_DECODE_FAIL),(unsigned)bm_get(BM_HCI_DECODE_FAIL),(unsigned)bm_get(BM_PORT5_HCI_DECODE_FAIL),(unsigned)bm_get(BM_READY_REJECT));
  printf("RADIO BTM RX_LOCK_FAIL=%u H4_ACL=%u H4_EVENT=%u H4_SCO=%u\n",
    (unsigned)bm_get(BM_RX_LOCK_FAIL),(unsigned)bm_get(BM_H4_ACL),(unsigned)bm_get(BM_H4_EVENT),(unsigned)bm_get(BM_H4_SCO));
  printf("RADIO BTM H4_VENDOR=%u H4_OTHER=%u LINK_ACK=%u FLOW_COMPLETE=%u\n",
    (unsigned)bm_get(BM_H4_VENDOR),(unsigned)bm_get(BM_H4_OTHER),(unsigned)bm_get(BM_LINK_ACK),(unsigned)bm_get(BM_FLOW_COMPLETE));
  printf("RADIO BTM last_send=%d last_decode=%d last_ready=%d last_wait=%d flow_status=%u\n",
    __atomic_load_n(&g_bt_meta.last_send_error,__ATOMIC_RELAXED),
    __atomic_load_n(&g_bt_meta.last_decode_error,__ATOMIC_RELAXED),
    __atomic_load_n(&g_bt_meta.last_ready_error,__ATOMIC_RELAXED),
    __atomic_load_n(&g_bt_meta.last_wait_error,__ATOMIC_RELAXED),
    (unsigned)__atomic_load_n(&g_bt_meta.flow_status,__ATOMIC_RELAXED));
  return 0;
}


static void reset(void){memset(&g_bt_meta,0,sizeof(g_bt_meta));g_bt_head=g_bt_tail=g_bt_count=0;g_bt_pending=false;g_bt_worker_fault=false;sent_result=wait_result=match_ack=wait_calls=lock_result=0;}
static void queue(void){uint8_t b[4]={0,0,0,5};assert(!bt_lower_send(0,b,4));assert(bm_get(BM_ACL_QUEUED)==1);}
int main(void){
 reset();queue();sent_result=-EIO;assert(bt_tx_worker(0,0)==-EIO);assert(bm_get(BM_ACL_SEND_FAIL)==1);assert(!bm_get(BM_ACL_SEND_OK));assert(!bm_get(BM_ACL_ACK_MATCH));
 reset();queue();match_ack=1;assert(bt_tx_worker(0,0)==-EINTR);assert(bm_get(BM_ACL_SEND_OK)==1&&bm_get(BM_ACL_ACK_MATCH)==1);
 assert(!bt_lower_ack(0,5,0));assert(bm_get(BM_ACL_ACK_OTHER)==1);
 reset();queue();wait_result=-ETIMEDOUT;assert(bt_tx_worker(0,0)==-ETIMEDOUT);assert(bm_get(BM_ACL_ACK_WAIT_FAIL)==1&&g_bt_meta.last_wait_error==-ETIMEDOUT);
 reset();g_bt_count=8;uint8_t b[4]={0,0,0,5};assert(bt_lower_send(0,b,4)==-EAGAIN);assert(!bm_get(BM_ACL_QUEUED));
 reset();lock_result=-EBUSY;assert(bt_lower_send(0,b,4)==-EBUSY);assert(!bm_get(BM_ACL_QUEUED));
 lock_result=0;assert(!fw_ble_status());assert(!bm_get(BM_ACL_QUEUED));puts("PASS extracted actual queue/worker/ACK functions: send failure, ACK match/unmatched, timeout, queue full, lock failure");return 0;
}
