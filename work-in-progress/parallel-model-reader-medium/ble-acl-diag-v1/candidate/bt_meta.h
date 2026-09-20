/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef K7_BT_META_H
#define K7_BT_META_H
#include <stdint.h>
#include <stddef.h>
/* Diagnostic only: no ordering, ownership or flow-control decisions. */
enum bm_counter { BM_ACL_QUEUED, BM_ACL_SEND_OK, BM_ACL_SEND_FAIL, BM_ACL_ACK_MATCH, BM_ACL_ACK_OTHER, BM_ACL_ACK_WAIT_FAIL, BM_PORT5_SLOT, BM_SLOT_DECODE_FAIL, BM_PORT5_SLOT_DECODE_FAIL, BM_HCI_DECODE_FAIL, BM_PORT5_HCI_DECODE_FAIL, BM_READY_REJECT, BM_RX_LOCK_FAIL, BM_H4_ACL, BM_H4_EVENT, BM_H4_SCO, BM_H4_VENDOR, BM_H4_OTHER, BM_LINK_ACK, BM_FLOW_COMPLETE, BM_COUNT };
struct bt_meta { uint32_t count[BM_COUNT]; int last_send_error, last_decode_error,
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
