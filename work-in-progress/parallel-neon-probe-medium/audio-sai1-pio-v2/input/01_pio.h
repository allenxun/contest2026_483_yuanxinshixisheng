/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef K7_SAI_PIO_H
#define K7_SAI_PIO_H
#include <stdint.h>
#define PIO_FRAMES 3200u
struct pio_port {
  void *ctx;
  int (*read)(void *, uint32_t offset, uint32_t *value);
  int (*write)(void *, uint32_t offset, uint32_t value);
  uint64_t (*us)(void *);
};
struct pio_result { unsigned frames, polls; int result, stop_result, held; };
struct pio_stats { int64_t sum[2]; int32_t min[2], max[2]; unsigned nonzero[2]; };
int pio_summarize(const uint32_t *, unsigned frames, struct pio_stats *);
/* Single caller, no IRQ/DMA/other SAI users. Callbacks bounded/nonblocking;
 * MMIO ordering supplied by port. prepared=true ONLY after root proves rails,
 * pinmux, actual mclk, codec I2S slave 32slot-compatible, amp policy and MMU.
 * capture requires space for 6400 uint32 words, preserves raw RX words.
 * playback generates stereo +/-2^20 signed32, 250Hz, at most200ms audio.
 * clock deadline250ms + up to2ms cleanup, also finite poll budgets.
 * Unknown version or pre-existing activity rejected without SAI writes.
 * held on cleanup failure: do not retry/reset/power-gate outside supervisor.
 * return0 is complete word transfer+stop, not microphone/acoustic acceptance. */
int pio_run(const struct pio_port *, int prepared, uint32_t actual_mclk,
            int playback, uint32_t *capture, unsigned capacity_words,
            struct pio_result *);
#endif
