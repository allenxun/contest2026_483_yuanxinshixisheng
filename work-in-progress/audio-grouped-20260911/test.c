#include "pio.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#undef assert
#define assert(condition) do { if (!(condition)) { \
  fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); return 1; \
} } while (0)

struct sim
{
  uint32_t reg[32];
  uint64_t now;
  unsigned cursor;
  unsigned group;
  unsigned levels[4];
  int mismatch;
  int no_data;
  int started;
};

static uint32_t levels(const struct sim *s)
{
  return s->levels[0] | (s->levels[1] << 6) |
         (s->levels[2] << 12) | (s->levels[3] << 18);
}

static uint64_t now_us(void *ctx)
{
  struct sim *s = ctx;
  s->now += 2;
  return s->now;
}

static int read_reg(void *ctx, uint32_t offset, uint32_t *value)
{
  struct sim *s = ctx;
  if (offset == 0x70) { *value = 0x23073576; return 0; }
  if (offset == 0x6c) { *value = 14; return 0; }
  if (offset == 0x14 || offset == 0x2c) { *value = 0; return 0; }
  if (offset == 0x1c) { *value = 0; return 0; }
  if (offset == 0x20)
    {
      *value = s->started && !s->no_data ? levels(s) : 0;
      return 0;
    }
  if (offset == 0x34)
    {
      unsigned bank = s->cursor / 2;
      if ((s->cursor & 1) == 0)
        {
          *value = UINT32_C(0x10000000) + s->group;
          if (s->mismatch && bank == 2) (*value)++;
          s->levels[bank] = 0;
        }
      else
        {
          *value = 0;
        }
      s->cursor++;
      if (s->cursor == 8)
        {
          s->cursor = 0;
          s->group++;
          for (bank = 0; bank < 4; bank++) s->levels[bank] = 1;
        }
      return 0;
    }
  *value = s->reg[offset / 4];
  return 0;
}

static int write_reg(void *ctx, uint32_t offset, uint32_t value)
{
  struct sim *s = ctx;
  s->reg[offset / 4] = value;
  if (offset == 0x10) s->started = !!(value & 8);
  return 0;
}

static int clocks(void *ctx) { (void)ctx; return 0; }
static int stream(void *ctx)
{
  struct sim *s = ctx;
  unsigned bank;
  for (bank = 0; bank < 4; bank++) s->levels[bank] = 1;
  return 0;
}
static int amp_off(void *ctx) { (void)ctx; return 0; }

static void initialize(struct sim *s)
{
  memset(s, 0, sizeof(*s));
  s->reg[0x38 / 4] = 0xe4e4;
}

int main(void)
{
  struct sim s;
  struct pio_result result;
  uint32_t capture[256];
  struct pio_port port = {&s, read_reg, write_reg, now_us,
                          clocks, stream, amp_off, 1u << 27};
  unsigned i;
  int rc;

  initialize(&s);
  rc = pio_run_grouped(&port, 1, 4096000, capture, 256, 128, &result);
  if (rc) fprintf(stderr, "first rc=%d frames=%u polls=%u stop=%d held=%d levels=%08x started=%d\n",
                  rc, result.frames, result.polls, result.stop_result,
                  result.held, levels(&s), s.started);
  assert(rc == 0);
  assert(result.frames == 128);
  assert(result.grouped_words == 2048);
  assert(result.grouped_mismatches == 0);
  assert(result.stop_result == 0 && result.held == 0);
  assert(s.reg[0x08 / 4] == 0x00700fff);
  assert(s.reg[0x38 / 4] == 0x000000e4);
  for (i = 0; i < 128; i++)
    {
      assert(capture[2 * i] == UINT32_C(0x10000000) + 2 * i);
      assert(capture[2 * i + 1] == UINT32_C(0x10000000) + 2 * i + 1);
    }

  initialize(&s);
  s.mismatch = 1;
  assert(pio_run_grouped(&port, 1, 4096000, capture, 256, 16,
                         &result) == 0);
  assert(result.grouped_mismatches == 32);

  initialize(&s);
  s.no_data = 1;
  assert(pio_run_grouped(&port, 1, 4096000, capture, 256, 16,
                         &result) == -110);
  assert(result.frames == 0 && result.grouped_words == 0 && !result.held);

  initialize(&s);
  assert(pio_run_grouped(&port, 1, 4096000, capture, 31, 16,
                         &result) == -22);
  assert(pio_run_grouped(&port, 1, 4096001, capture, 256, 16,
                         &result) == -22);

  puts("PASS grouped RXDR cycle, copy agreement diagnostics, timeout and bounds");
  return 0;
}
