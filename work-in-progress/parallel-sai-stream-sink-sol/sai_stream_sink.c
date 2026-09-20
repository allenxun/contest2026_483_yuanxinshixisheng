#include "sai_stream_sink.h"

#include <string.h>

static int expired(struct ss_sink *s, uint64_t deadline)
{
  return s->ops.now_us(s->ops.ctx) >= deadline;
}

static int cleanup(struct ss_sink *s, uint64_t deadline)
{
  int first = 0;
  int rc;

  if (!s || !s->owned) return SS_OK;
  /* Every stage is attempted. Later cleanup never hides an earlier failure. */
  rc = s->ops.amp_off_fast(s->ops.ctx);
  if (rc && !first) first = rc;
  if (s->cleanup_armed) {
    rc = s->ops.stop_tx(s->ops.ctx, deadline);
    if (rc && !first) first = rc;
    rc = s->ops.codec_stop(s->ops.ctx, deadline);
    if (rc && !first) first = rc;
    rc = s->ops.platform_cleanup(s->ops.ctx, deadline);
    if (rc && !first) first = rc;
  }
  s->ops.owner_release(s->ops.ctx, first != 0);
  s->owned = 0;
  s->cleanup_armed = 0;
  s->started = 0;
  if (first) {
    s->held = 1;
    s->state = SS_FAULT;
    return SS_CLEANUP;
  }
  s->state = SS_IDLE;
  return SS_OK;
}

static int fail(struct ss_sink *s, int primary, uint64_t deadline)
{
  return cleanup(s, deadline) == SS_OK ? primary : SS_CLEANUP;
}

static int start(struct ss_sink *s, uint64_t deadline)
{
  int rc;
  if (s->started) return SS_OK;
  if (expired(s, deadline)) return fail(s, SS_TIMEOUT, deadline);
  rc = s->ops.start_tx(s->ops.ctx);
  if (rc) return fail(s, SS_IO, deadline);
  s->started = 1;
  rc = s->ops.enable_amp(s->ops.ctx);
  if (rc) return fail(s, SS_IO, deadline);
  s->state = SS_RUNNING;
  return SS_OK;
}

int ss_init(struct ss_sink *s, const struct ss_ops *ops)
{
  if (!s || !ops || !ops->now_us || !ops->cancelled ||
      !ops->owner_try_acquire || !ops->owner_release || !ops->prepare_tx ||
      !ops->fifo_words || !ops->write_word || !ops->start_tx ||
      !ops->enable_amp || !ops->amp_off_fast || !ops->stop_tx ||
      !ops->codec_stop || !ops->platform_cleanup) return SS_INVALID;
  memset(s, 0, sizeof(*s));
  s->ops = *ops;
  s->fifo_capacity_words = 16;
  s->prefill_words = 16;
  s->polls_per_call = 4096;
  return SS_OK;
}

int ss_begin(struct ss_sink *s, uint32_t rate, unsigned channels,
             uint64_t deadline)
{
  int rc;
  if (!s || rate != 16000 || channels != 2 || s->held) return SS_INVALID;
  if (s->state != SS_IDLE || s->owned) return SS_BUSY;
  if (expired(s, deadline)) return SS_TIMEOUT;
  rc = s->ops.owner_try_acquire(s->ops.ctx);
  if (rc) return SS_BUSY;
  s->owned = 1;
  if (s->ops.cancelled(s->ops.ctx)) return fail(s, SS_CANCELLED, deadline);
  /* prepare_tx may fail after partially touching every hardware layer. */
  s->cleanup_armed = 1;
  rc = s->ops.prepare_tx(s->ops.ctx, deadline);
  if (rc) return fail(s, SS_IO, deadline);
  s->state = SS_READY;
  s->accepted_frames = 0;
  s->write_calls = 0;
  return SS_OK;
}

ptrdiff_t ss_write(struct ss_sink *s, const int32_t *stereo, size_t frames,
                   uint64_t deadline)
{
  unsigned polls = 0;
  size_t accepted = 0;
  if (!s || !stereo || !frames || !s->owned || !s->cleanup_armed ||
      (s->state != SS_READY && s->state != SS_RUNNING)) return SS_INVALID;
  s->write_calls++;
  while (accepted < frames) {
    unsigned level;
    if (s->ops.cancelled(s->ops.ctx))
      return fail(s, SS_CANCELLED, deadline);
    if (expired(s, deadline) || polls++ >= s->polls_per_call)
      return fail(s, SS_TIMEOUT, deadline);
    if (s->ops.fifo_words(s->ops.ctx, &level) ||
        level > s->fifo_capacity_words)
      return fail(s, SS_IO, deadline);
    if (level + 2 > s->fifo_capacity_words) {
      if (accepted) break;
      continue;
    }
    if (s->ops.write_word(s->ops.ctx, (uint32_t)stereo[2 * accepted]) ||
        s->ops.write_word(s->ops.ctx, (uint32_t)stereo[2 * accepted + 1]))
      return fail(s, SS_IO, deadline);
    accepted++;
    s->accepted_frames++;
    level += 2;
    if (!s->started && level >= s->prefill_words) {
      int rc = start(s, deadline);
      if (rc) return rc;
    }
  }
  return (ptrdiff_t)accepted;
}

int ss_drain(struct ss_sink *s, uint64_t deadline)
{
  unsigned polls = 0;
  unsigned level;
  int rc;
  if (!s || !s->owned || !s->cleanup_armed) return SS_INVALID;
  if (s->ops.cancelled(s->ops.ctx)) return fail(s, SS_CANCELLED, deadline);
  if (!s->started) {
    if (!s->accepted_frames) return SS_OK;
    rc = start(s, deadline);
    if (rc) return rc;
  }
  for (;;) {
    if (s->ops.cancelled(s->ops.ctx)) return fail(s, SS_CANCELLED, deadline);
    if (expired(s, deadline) || polls++ >= s->polls_per_call)
      return fail(s, SS_TIMEOUT, deadline);
    if (s->ops.fifo_words(s->ops.ctx, &level) ||
        level > s->fifo_capacity_words) return fail(s, SS_IO, deadline);
    if (!level) return SS_OK;
  }
}

int ss_abort(struct ss_sink *s, uint64_t deadline)
{
  if (!s) return SS_INVALID;
  return cleanup(s, deadline);
}

int ss_end(struct ss_sink *s, uint64_t deadline)
{
  int rc;
  int clean;
  if (!s) return SS_INVALID;
  if (!s->owned) return s->state == SS_FAULT ? SS_CLEANUP : SS_OK;
  rc = ss_drain(s, deadline);
  if (!s->owned) return rc;
  clean = cleanup(s, deadline);
  return clean == SS_OK ? rc : clean;
}
