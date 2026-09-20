#ifndef PARALLEL_SAI_STREAM_SINK_H
#define PARALLEL_SAI_STREAM_SINK_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum ss_result {
  SS_OK = 0,
  SS_INVALID = -22,
  SS_IO = -5,
  SS_BUSY = -16,
  SS_CANCELLED = -125,
  SS_TIMEOUT = -110,
  SS_CLEANUP = -117
};

enum ss_state { SS_IDLE, SS_READY, SS_RUNNING, SS_FAULT };

/* All callbacks are synchronous, serialized and bounded by deadline_us.
 * prepare_tx establishes the existing raw32/16k stereo profile with CLK/FS
 * running, TX stopped, FIFO empty, codec armed and amplifier physically low.
 * owner_try_acquire is shared with capture: playback and recording therefore
 * cannot own SAI1/codec at the same time. */
struct ss_ops {
  void *ctx;
  uint64_t (*now_us)(void *);
  int (*cancelled)(void *);
  int (*owner_try_acquire)(void *);
  /* held=1 latches the shared playback/capture gate after uncertain cleanup. */
  void (*owner_release)(void *, int held);
  int (*prepare_tx)(void *, uint64_t deadline_us);
  /* Check/clear-report TX underrun first, then return summed TXFIFOLR words. */
  int (*fifo_words)(void *, unsigned *words);
  int (*write_word)(void *, uint32_t word);
  int (*start_tx)(void *);
  int (*enable_amp)(void *);
  int (*amp_off_fast)(void *);
  int (*stop_tx)(void *, uint64_t deadline_us);
  int (*codec_stop)(void *, uint64_t deadline_us);
  int (*platform_cleanup)(void *, uint64_t deadline_us);
};

struct ss_sink {
  struct ss_ops ops;
  enum ss_state state;
  unsigned fifo_capacity_words;
  unsigned prefill_words;
  unsigned polls_per_call;
  unsigned accepted_frames;
  unsigned write_calls;
  int owned;
  int cleanup_armed;
  int started;
  int held;
};

int ss_init(struct ss_sink *, const struct ss_ops *);
int ss_begin(struct ss_sink *, uint32_t sample_rate, unsigned channels,
             uint64_t deadline_us);
/* Returns an accepted frame count. A positive short write is normal. */
ptrdiff_t ss_write(struct ss_sink *, const int32_t *stereo, size_t frames,
                   uint64_t deadline_us);
int ss_drain(struct ss_sink *, uint64_t deadline_us);
/* abort and end are idempotent after a successful cleanup. */
int ss_abort(struct ss_sink *, uint64_t deadline_us);
int ss_end(struct ss_sink *, uint64_t deadline_us);

#ifdef __cplusplus
}
#endif
#endif
