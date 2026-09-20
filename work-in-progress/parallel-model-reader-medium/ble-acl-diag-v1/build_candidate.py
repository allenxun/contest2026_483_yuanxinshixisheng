from pathlib import Path
import hashlib,json,difflib
root=Path('E:/openvela/VelaVision'); d=root/'work-in-progress/parallel-model-reader-medium/ble-acl-diag-v1'
(d/'input').mkdir(exist_ok=True); (d/'candidate').mkdir(exist_ok=True)
inputs=[]
for n in ['k7radio_main.c','skw_bt.c','skw_bt.h','skw_native.h','skw_packet.c']:
 b=(d/'input'/n).read_bytes() if (d/'input'/n).exists() else (root/'app/k7radio'/n).read_bytes(); (d/'input'/n).write_bytes(b); (d/'candidate'/n).write_bytes(b)
 inputs.append(dict(path='app/k7radio/'+n,sha256=hashlib.sha256(b).hexdigest()))
(d/'inputs.json').write_text(json.dumps(inputs,indent=2))
fields=['ACL_QUEUED','ACL_SEND_OK','ACL_SEND_FAIL','ACL_ACK_MATCH','ACL_ACK_OTHER','ACL_ACK_WAIT_FAIL','PORT5_SLOT','SLOT_DECODE_FAIL','PORT5_SLOT_DECODE_FAIL','HCI_DECODE_FAIL','PORT5_HCI_DECODE_FAIL','READY_REJECT','RX_LOCK_FAIL','H4_ACL','H4_EVENT','H4_SCO','H4_VENDOR','H4_OTHER','LINK_ACK','FLOW_COMPLETE']
h='''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef K7_BT_META_H
#define K7_BT_META_H
#include <stdint.h>
#include <stddef.h>
/* Diagnostic only: no ordering, ownership or flow-control decisions. */
'''
h+='enum bm_counter { '+', '.join('BM_'+x for x in fields)+', BM_COUNT };\n'
h+='''struct bt_meta { uint32_t count[BM_COUNT]; int last_send_error, last_decode_error,
 last_ready_error, last_wait_error; uint32_t flow_status; };
extern struct bt_meta g_bt_meta;
_Static_assert(sizeof(int) == 4, "diagnostic error width");
_Static_assert(__atomic_always_lock_free(4, 0), "32-bit diagnostics require lock-free atomics");
static inline void bm_inc(enum bm_counter c)
{ __atomic_fetch_add(&g_bt_meta.count[c], 1u, __ATOMIC_RELAXED); }
static inline uint32_t bm_get(enum bm_counter c)
{ return __atomic_load_n(&g_bt_meta.count[c], __ATOMIC_RELAXED); }
static inline void bm_error(int *dst, int error)
{ __atomic_store_n(dst, error, __ATOMIC_RELAXED); }
static inline void bm_send(unsigned channel, int ret)
{
 if (channel != 5) return;
 bm_inc(ret ? BM_ACL_SEND_FAIL : BM_ACL_SEND_OK);
 if (ret) bm_error(&g_bt_meta.last_send_error, ret);
}
static inline void bm_slot(unsigned channel, int ret)
{
 if (channel == 5) bm_inc(BM_PORT5_SLOT);
 if (ret) { if (channel == 5) bm_inc(BM_PORT5_SLOT_DECODE_FAIL); bm_inc(BM_SLOT_DECODE_FAIL); bm_error(&g_bt_meta.last_decode_error, ret); }
}
static inline void bm_h4(const uint8_t *p, size_t n)
{
 if (n == 12) { bm_inc(BM_LINK_ACK); return; }
 if (n < 13) { bm_inc(BM_H4_OTHER); return; }
 switch(p[12]) {
 case 2: bm_inc(BM_H4_ACL); break;
 case 4: bm_inc(BM_H4_EVENT); break;
 case 3: bm_inc(BM_H4_SCO); break;
 case 7: bm_inc(BM_H4_VENDOR); break;
 default: bm_inc(BM_H4_OTHER); break;
 }
}
#endif
'''
(d/'candidate/bt_meta.h').write_text(h)
def edit(n,old,new):
 p=d/'candidate'/n; s=p.read_text(); assert s.count(old)==1,(n,old,s.count(old)); p.write_text(s.replace(old,new))
edit('k7radio_main.c','#include "skw_bt.h"','#include "skw_bt.h"\n#include "bt_meta.h"\nstruct bt_meta g_bt_meta;')
edit('k7radio_main.c','          if (ret) return fw_rx_fault("sdio2", ret, i, bytes);','          bm_slot(g_rx[i * SKW_RX_SLOT_SIZE + 3], ret);\n          if (ret) return fw_rx_fault("sdio2", ret, i, bytes);')
edit('k7radio_main.c','  g_bt_tail = (g_bt_tail + 1) % 8; g_bt_count++;','  g_bt_tail = (g_bt_tail + 1) % 8; g_bt_count++;\n  if (length >= 4 && ((const uint8_t *)packet)[3] == SKW_BT_DATA_PORT) bm_inc(BM_ACL_QUEUED);')
edit('k7radio_main.c','      __atomic_add_fetch(&g_bt_host_ack, 1, __ATOMIC_RELAXED);','      __atomic_add_fetch(&g_bt_host_ack, 1, __ATOMIC_RELAXED);\n      if (channel == SKW_BT_DATA_PORT) bm_inc(BM_ACL_ACK_MATCH);')
edit('k7radio_main.c','      nxsem_post(&g_bt_acksem);\n    }\n  return 0;','      nxsem_post(&g_bt_acksem);\n    }\n  else if (channel == SKW_BT_DATA_PORT) bm_inc(BM_ACL_ACK_OTHER);\n  return 0;')
edit('k7radio_main.c','      ret = fw_packet(true, g_bt_current.data, g_bt_current.length);','      ret = fw_packet(true, g_bt_current.data, g_bt_current.length);\n      bm_send(g_bt_current.data[3], ret);')
edit('k7radio_main.c','      ret = nxsem_tickwait_uninterruptible(&g_bt_acksem, MSEC2TICK(1500));','      ret = nxsem_tickwait_uninterruptible(&g_bt_acksem, MSEC2TICK(1500));\n      if (ret && g_bt_current.data[3] == SKW_BT_DATA_PORT)\n        { bm_inc(BM_ACL_ACK_WAIT_FAIL); bm_error(&g_bt_meta.last_wait_error, ret); }')
printlines='\n  /* Relaxed atomic reads: each field valid; this is not a coherent snapshot. */\n'
for i in range(0,len(fields),4):
 fs=fields[i:i+4]; printlines+='  printf("RADIO BTM '+ ' '.join(x+'=%u' for x in fs)+'\\n",\n    '+','.join('(unsigned)bm_get(BM_'+x+')' for x in fs)+');\n'
printlines+='  printf("RADIO BTM last_send=%d last_decode=%d last_ready=%d last_wait=%d flow_status=%u\\n",\n    __atomic_load_n(&g_bt_meta.last_send_error,__ATOMIC_RELAXED),\n    __atomic_load_n(&g_bt_meta.last_decode_error,__ATOMIC_RELAXED),\n    __atomic_load_n(&g_bt_meta.last_ready_error,__ATOMIC_RELAXED),\n    __atomic_load_n(&g_bt_meta.last_wait_error,__ATOMIC_RELAXED),\n    (unsigned)__atomic_load_n(&g_bt_meta.flow_status,__ATOMIC_RELAXED));\n'
edit('k7radio_main.c','  nxmutex_unlock(&g_native_bt.lock);\n  return 0;','  nxmutex_unlock(&g_native_bt.lock);'+printlines+'  return 0;')
edit('skw_bt.c','#include "skw_bt.h"','#include "skw_bt.h"\n#include "bt_meta.h"')
edit('skw_bt.c','  ret = skw_hci_decode(&packet, &hci);','  bm_h4(packet.payload, packet.length);\n  ret = skw_hci_decode(&packet, &hci);\n  if (ret) { if (packet.channel == SKW_BT_DATA_PORT) bm_inc(BM_PORT5_HCI_DECODE_FAIL); bm_inc(BM_HCI_DECODE_FAIL); bm_error(&g_bt_meta.last_decode_error, ret); }')
edit('skw_bt.c','  if (!bt->opened) ret = -ENOTCONN;','  if (!bt->opened) ret = -ENOTCONN;') # unique anchor unchanged
edit('skw_bt.c','  else ret = ready(bt);','  else ret = ready(bt);\n  if (ret) { bm_inc(BM_READY_REJECT); bm_error(&g_bt_meta.last_ready_error, ret); }')
edit('skw_bt.c','          uint16_t op=p[3] | p[4]<<8;','          uint16_t op=p[3] | p[4]<<8;\n          if (op == 0x0c31)\n            { __atomic_store_n(&g_bt_meta.flow_status, p[5], __ATOMIC_RELAXED); bm_inc(BM_FLOW_COMPLETE); }')
# RX-only lock failure anchor
edit('skw_bt.c','  if (ret) return ret;\n  if (!bt->opened) ret = -ENOTCONN;','  if (ret) { bm_inc(BM_RX_LOCK_FAIL); bm_error(&g_bt_meta.last_ready_error, ret); return ret; }\n  if (!bt->opened) ret = -ENOTCONN;')
patch=''
for n in ['k7radio_main.c','skw_bt.c','bt_meta.h']:
 old=(d/'input'/n).read_text().splitlines(True) if (d/'input'/n).exists() else []
 patch+=''.join(difflib.unified_diff(old,(d/'candidate'/n).read_text().splitlines(True),fromfile='a/app/k7radio/'+n if old else '/dev/null',tofile='b/app/k7radio/'+n))
(d/'candidate.patch').write_text(patch)
print('generated candidate')
