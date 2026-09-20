/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef K7_SAI_PIO_V3_H
#define K7_SAI_PIO_V3_H
#include <stdint.h>
#define PIO_FRAMES 48000u
#define PIO_MAX_AMPLITUDE (UINT32_C(1)<<27)
struct pio_port {
 void *ctx;
 int (*read)(void *,uint32_t,uint32_t *);
 int (*write)(void *,uint32_t,uint32_t);
 uint64_t (*us)(void *);
 /* Called after CLK/FS start, before either stream or TX prefill. May call
  * kd_arm with bounded I2C/delay and AMP LOW, within100ms, no reentry.
  * Nonzero is failure even if it partially enabled codec/amp. */
 int (*clocks_started)(void *);
 /* Immediately after TXS/RXS, pureGPIO kd_enable_amp, <100us, no I2C/delay. */
 int (*streams_started)(void *);
 /* Always called on post-configuration exit, before stream stop. Idempotent
  * fast amp-off MMIO only (<100us), NO I2C/delay/codec teardown here.
  * Root may do codec mute/I2C after stream stop; failure retains held. */
 int (*amp_off_fast)(void *);
 uint32_t amplitude; /* 1..2^27; applies to playback signed32 tone */
};
#define PIO_RX_TRACE_MAX 32u
struct pio_rx_trace_entry {
 uint64_t time_us;
 uint32_t fifo_before,word,fifo_after;
 int before_rc,word_rc,after_rc;
};
struct pio_rx_trace {
 /* Sampling window: after stream hook, before cleanup. Zero when not entered.
  * init[] order MONO_CR,RX_SHIFT,RXCR,PATH_SEL,DMACR,XFER; negative rc means
  * invalid value. Snapshots sequential, not atomic; tracing perturbs timing. */
 uint64_t start_us,end_us;
 uint32_t init[6];int init_rc[6];
 unsigned window_started,count;
 struct pio_rx_trace_entry entry[PIO_RX_TRACE_MAX];
};
struct pio_result {
 unsigned frames,polls,prefill_words,max_fifo;
 uint32_t first_fifo_raw,last_fifo_raw;
 int result,stop_result,held,activation_result,start_result,amp_off_result;
 struct pio_rx_trace rx_trace;
};
struct pio_stats {int64_t sum[2];int32_t min[2],max[2];unsigned nonzero[2];};
int pio_summarize(const uint32_t *,unsigned,struct pio_stats *);
/* Sum four6-bit fields as vendor get_fifo_count; never infer physical bank
 * distribution or sample format from one field. Reserved high bits ignored. */
unsigned pio_fifo_count(uint32_t);
/* V1 platform prerequisites retained: exclusive, codec raw32, actualMCLK,
 * IRQ/DMA off, MMIO ordering, nonblocking read/write/time, VERSION23073576.
 * Exactly16 prefill words with TX stopped; sum4 readback must be16. During TX
 * enqueue pair only at count<=14; never knowingly exceed16. Observed FIFO
 * occupancy total is recorded; first/last raw registers preserve all fields.
 * For RX first raw is first loop observation (may be zero); TX is prefill.
 * Full physical depth >=16 inferred from vendor
 * threshold16/maxburst8, still requires actual FIFO evidence on this board.
 * Capture capacity>=2*frames, frames1..48000 (384000bytes maximum).
 * Playback frames8..3200 only; first root probe uses3200. Transfer deadline
 * frames/16000 seconds +100ms begins after hook; polls limited4096/frame.
 * Callback deadline checked after return (cannot interrupt blocked callback).
 * amplitude bound is digital only; root must enforce safe codec/amp gain.
 * Result success requires transfer+ampoff+SAI stop; codec teardown afterward.
 */
int pio_run(const struct pio_port *,int prepared,uint32_t actual_mclk,
 int playback,uint32_t *capture,unsigned capacity_words,unsigned frames,
 struct pio_result *);
/* Read-only rawPCM32 interleaved L,R buffer, frames1..48000; words>=2*frames.
 * Caller owns immutable storage, nonoverlapping result/port, for full call.
 * Exact words sent, no synthesis/zero padding/gain/format conversion; caller
 * must pass only actual captured frames, not unused capacity. amplitude field
 * does NOT attenuate this API. Root controls safe codec/amp gain. Hardware
 * cannot prove source provenance; caller must retain real capture evidence.
 * Short inputs prefill min(16,2*frames), exact FIFO sum must match that count.
 * Existing tone pio_run API/limits and all terminal logic remain unchanged. */
int pio_play_buffer(const struct pio_port *,int prepared,uint32_t actual_mclk,
 const uint32_t *source,unsigned source_words,unsigned frames,struct pio_result *);
#endif
