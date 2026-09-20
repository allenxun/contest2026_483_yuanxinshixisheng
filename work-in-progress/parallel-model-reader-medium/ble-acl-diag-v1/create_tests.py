from pathlib import Path
p=Path(__file__).parent
files={
'stubs/nuttx/config.h':'#define CONFIG_IOB_BUFSIZE 256\n',
'stubs/nuttx/mutex.h':'''#include <pthread.h>
typedef pthread_mutex_t mutex_t;
extern int mock_lock_error;
static inline int nxmutex_init(mutex_t *m) { return pthread_mutex_init(m,0); }
static inline int nxmutex_lock(mutex_t *m) { return mock_lock_error ? mock_lock_error : pthread_mutex_lock(m); }
static inline int nxmutex_unlock(mutex_t *m) { return pthread_mutex_unlock(m); }
''',
'stubs/nuttx/wireless/bluetooth/bt_driver.h':'''#include <stddef.h>
enum bt_buf_type_e { BT_CMD, BT_ACL_OUT, BT_EVT, BT_ACL_IN };
struct bt_driver_s { void *priv; int (*open)(struct bt_driver_s *); void (*close)(struct bt_driver_s *);
int (*send)(struct bt_driver_s *, enum bt_buf_type_e, void *, size_t);
int (*receive)(void); unsigned head_reserve; };
''',
'stubs/nuttx/net/bluetooth.h':'''#define BLUETOOTH_MAX_FRAMELEN 256
int bt_netdev_receive(struct bt_driver_s *, enum bt_buf_type_e, void *, size_t);
''',
'test.c':r'''#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "skw_bt.h"
#include "bt_meta.h"
struct bt_meta g_bt_meta;
int mock_lock_error, mock_ready_error;
static int ready_cb(void *x) { (void)x; return mock_ready_error; }
static int send_cb(void *x,const void *p,size_t n) {(void)x;(void)p;(void)n;return 0;}
static int ack_cb(void *x,uint8_t c,uint16_t s) {(void)x;(void)c;(void)s;return 0;}
static int recv_cb(void) {return 0;}
int bt_netdev_receive(struct bt_driver_s *b,enum bt_buf_type_e t,void *v,size_t n)
{(void)b;(void)t;(void)v;(void)n;return 0;}
static size_t slot(unsigned char *b,unsigned type) {
 unsigned char payload[32]={0}; size_t n;
 payload[12]=(unsigned char)type;
 if(type==4) {payload[13]=0x0e;payload[14]=4;payload[15]=1;payload[16]=0x31;payload[17]=0x0c;payload[18]=0x0c;}
 assert(!skw_sdio2_encode(type==4?2:5,payload,type==4?19:17,b,2048,&n));return n;
}
static void *count_thread(void *p) {(void)p;for(int i=0;i<100000;i++)bm_inc(BM_ACL_QUEUED);return 0;}
int main(void) {
 struct skw_bt b; struct skw_bt_lower lower={ready_cb,send_cb,ack_cb}; unsigned char data[2048]; size_t n;
 assert(!skw_bt_init(&b,&lower,0)); b.driver.receive=recv_cb;
 n=slot(data,2);assert(skw_bt_receive_slot(&b,data,n)==-ENOTCONN);assert(bm_get(BM_READY_REJECT)==1);
 assert(!b.driver.open(&b.driver));
 mock_ready_error=-EIO; assert(skw_bt_receive_slot(&b,data,n)==-EIO);mock_ready_error=0;
 mock_lock_error=-EBUSY;assert(skw_bt_receive_slot(&b,data,n)==-EBUSY);mock_lock_error=0;
 assert(bm_get(BM_RX_LOCK_FAIL)==1);assert(bm_get(BM_READY_REJECT)==2);
 assert(!skw_bt_receive_slot(&b,data,n));assert(b.acl_rx==1);
 data[16]=9;assert(skw_bt_receive_slot(&b,data,n)==-EPROTO);assert(bm_get(BM_HCI_DECODE_FAIL)==1&&bm_get(BM_PORT5_HCI_DECODE_FAIL)==1);assert(bm_get(BM_H4_OTHER)==1);
 n=slot(data,4);assert(!skw_bt_receive_slot(&b,data,n));assert(bm_get(BM_FLOW_COMPLETE)==1);assert(g_bt_meta.flow_status==12);
 bm_slot(5,-EMSGSIZE);bm_slot(2,0);assert(bm_get(BM_PORT5_SLOT)==1&&bm_get(BM_SLOT_DECODE_FAIL)==1&&bm_get(BM_PORT5_SLOT_DECODE_FAIL)==1);
 bm_send(2,-EIO);bm_send(5,-EIO);bm_send(5,0);assert(bm_get(BM_ACL_SEND_FAIL)==1&&bm_get(BM_ACL_SEND_OK)==1);assert(g_bt_meta.last_send_error==-EIO);
 pthread_t t[4];for(int i=0;i<4;i++)assert(!pthread_create(&t[i],0,count_thread,0));for(int i=0;i<4;i++)assert(!pthread_join(t[i],0));assert(bm_get(BM_ACL_QUEUED)==400000);
 __atomic_store_n(&g_bt_meta.count[BM_ACL_QUEUED],UINT32_MAX,__ATOMIC_RELAXED);bm_inc(BM_ACL_QUEUED);assert(bm_get(BM_ACL_QUEUED)==0);
 assert(!pthread_mutex_destroy(&b.lock));puts("PASS real skw_bt RX failures/H4/flow + send/slot helpers + 4x100000 atomic increments/wrap");return 0;
}
'''
}
for n,s in files.items():
 q=p/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s)

