/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SAI_DUPLEX_DIAG_H
#define SAI_DUPLEX_DIAG_H
#include <stdint.h>
#define DL_MAX_FRAMES 256u
#define DL_TRACE 64u
struct dl_port {
 void *ctx;
 int (*read)(void *,uint32_t,uint32_t *);
 int (*write)(void *,uint32_t,uint32_t);
 uint64_t (*us)(void *);
 /* Idempotent pure GPIO force-low AND verify; no enable callback exists. */
 int (*amp_low)(void *);
};
struct dl_word {uint64_t us;uint32_t before,word,after;int rc;};
struct dl_result {
 int result,stop_rc,restore_rc,amp_rc,held;
 unsigned frames,tx_words,polls,ntx,nrx,max_tx,max_rx;
 uint64_t start_us,end_us;
 uint32_t path_before,path_active,path_restored;
 struct dl_word tx[DL_TRACE],rx[DL_TRACE];
};
/* Exclusive owner; powered SAI; callbacks nonblocking/ordered; same-CPU.
 * common_clock_verified confirms same-SAI shared CKR/FSCR master route.
 * No codec hook, amp enable, DMA, allocation or print. frames 8..256.
 * Capture/port/result must not alias. Caller owns capture >=2*frames words.
 * Error held forbids clock/power teardown; restore/stop must be checked.
 * Does not assert marker correctness: captures raw zeros and all data. */
int dl_run(const struct dl_port *,int prepared,int common_clock_verified,
 uint32_t mclk,uint32_t *capture,unsigned capacity,unsigned frames,
 struct dl_result *);
#endif
