/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "i2c_owner.inc"
#include <stdlib.h>
#include <unistd.h>
#include "codec_duplex.h"
#include "pio.h"
#include "platform.h"
#define BIT(n) (UINT32_C(1) << (n))
#define GENMASK(h,l) ((UINT32_MAX >> (31-(h))) & (UINT32_MAX << (l)))
#include "input/rockchip_sai.h"
#define SAI ((uintptr_t)0x2a610000)
#define GPIO2 ((uintptr_t)0x2ae20000)
static struct kd_codec codec;
static struct sap_state platform;
static uint32_t capture[96000];
static unsigned captured_frames;
static bool playing, amp_ready, data_held;
static uint32_t old_audio_root, old_audio_gate;

static int abs_read(void *ctx, uintptr_t addr, uint32_t *value)
{
  *value = rd(ctx, addr);
  return 0;
}
static int abs_write(void *ctx, uintptr_t addr, uint32_t value)
{
  wr(ctx, addr, value);
  return 0;
}
static int sai_read(void *ctx, uint32_t offset, uint32_t *value)
{
  if (!platform.ready || offset > 0x70 || (offset & 3)) return -EINVAL;
  return abs_read(ctx, SAI + offset, value);
}
static int sai_write(void *ctx, uint32_t offset, uint32_t value)
{
  if (!platform.ready || offset > 0x68 || (offset & 3)) return -EINVAL;
  return abs_write(ctx, SAI + offset, value);
}
static uint64_t now_ms(void *ctx) { return now_us(ctx) / 1000; }
static int codec_write(void *ctx, uint8_t address, uint8_t reg,
                       uint8_t value, uint64_t deadline)
{
  (void)ctx;
  if (address != 0x10 || now_ms(NULL) >= deadline) return -ETIMEDOUT;
  uint64_t stamp = now_ms(NULL);
  if (stamp >= deadline) return -ETIMEDOUT;
  uint64_t remaining = (deadline - stamp) * 1000;
  if (!remaining) return -ETIMEDOUT;
  int rc = i3_xfer(&bus, false, reg, &value, remaining > 100000 ? 100000 : remaining);
  if (rc) printf("SOUND codec_write reg=%02x error=%d\n", reg, rc);
  return rc;
}
static int codec_read(void *ctx, uint8_t address, uint8_t reg,
                      uint8_t *value, uint64_t deadline)
{
  (void)ctx;
  if (address != 0x10 || now_ms(NULL) >= deadline) return -ETIMEDOUT;
  uint64_t stamp = now_ms(NULL);
  if (stamp >= deadline) return -ETIMEDOUT;
  uint64_t remaining = (deadline - stamp) * 1000;
  if (!remaining) return -ETIMEDOUT;
  int rc = i3_xfer(&bus, true, reg, value, remaining > 100000 ? 100000 : remaining);
  if (rc) printf("SOUND codec_read reg=%02x error=%d\n", reg, rc);
  return rc;
}
static int delay_ms(void *ctx, unsigned ms, uint64_t deadline)
{
  (void)ctx;
  uint64_t end = now_ms(NULL) + ms;
  if (end >= deadline) return -ETIMEDOUT;
  while (now_ms(NULL) < end) usleep(1000);
  return 0;
}
static int amplifier(void *ctx, bool on, uint64_t deadline)
{
  (void)ctx;
  if (!amp_ready || now_ms(NULL) >= deadline) return -EIO;
  masked(GPIO2, 1u << 9, on ? 1u << 9 : 0);
  return (rd(NULL, GPIO2) & (1u << 9)) == (on ? 1u << 9 : 0) ? 0 : -EIO;
}
static int amp_prepare(void)
{
  if (rd(NULL, CRU + 0xa48) & 6) return -EBUSY;
  masked(CRU + 0x848, 2, 0);
  if (rd(NULL, CRU + 0x848) & 2) return -EIO;
  uint32_t version = rd(NULL, GPIO2 + 0x78);
  if (version != 0x01000c2b && version != 0x0101157c && version != 0x010219c8) return -ENODEV;
  /* Program a low output before selecting GPIO2_B1; leave it LOW at exit. */
  masked(GPIO2, 1u << 9, 0);
  masked(GPIO2 + 8, 1u << 9, 1u << 9);
  masked(0x26044048, 0xf0, 0);
  if ((rd(NULL, GPIO2) & 0x200) || !(rd(NULL, GPIO2 + 8) & 0x200) ||
      (rd(NULL, 0x26044048) & 0xf0)) return -EIO;
  amp_ready = true;
  return 0;
}
static int codec_ready(void *ctx, unsigned bits, uint32_t mclk,
                       uint32_t bclk, bool cap, bool play, uint64_t deadline)
{
  (void)ctx;
  if (now_ms(NULL) >= deadline || !platform.ready || bits != 32 ||
      mclk != 4096000 || bclk != 1024000 ||
      rd(NULL, CRU + 0x330) != 0x00400177 ||
      (rd(NULL, CRU + 0x334) & 3) != 3 ||
      (rd(NULL, CRU + 0x3b8) & 0xfff) != 0x100 ||
      (rd(NULL, CRU + 0x820) & 0x70)) return -EIO;
  uint32_t xfer = rd(NULL, SAI + SAI_XFER);
  if (xfer & 0xc) return -EBUSY;
  if (cap || play)
    {
      if ((xfer & 3) != 3) return -EIO;
      /* PIO establishes CKR divider4 and raw32 format before this callback. */
      if (((rd(NULL, SAI + SAI_CKR) >> 3) & 0xfff) != 3) return -EIO;
    }
  return 0;
}
static int quiesce(void *ctx, uint64_t deadline)
{
  (void)ctx;
  if (now_ms(NULL) >= deadline || data_held) return -EBUSY;
  return (rd(NULL, SAI + SAI_XFER) & 0xf) ||
         (rd(NULL, SAI + SAI_DMACR) & (SAI_DMACR_RDE_MASK | SAI_DMACR_TDE_MASK)) ? -EBUSY : 0;
}
static int arm_codec(void *ctx)
{
  (void)ctx;
  return kd_arm(&codec, !playing, playing, now_ms(NULL) + 100);
}
static int enable_amp(void *ctx)
{
  (void)ctx;
  return playing ? kd_enable_amp(&codec, now_ms(NULL) + 10) : 0;
}
static int amp_off(void *ctx)
{
  return amplifier(ctx, false, now_ms(NULL) + 10);
}

int main(int argc, char **argv)
{
  if (argc < 2 || argc > 3) { puts("usage: k7sound probe|tone|capture [frames]|dump"); return 1; }
  if (pthread_mutex_trylock(&owner)) return 1;
  if (!strcmp(argv[1], "dump"))
    {
      printf("SOUND_PCM frames=%u rate=16000 channels=2 bits=32\n", captured_frames);
      for (unsigned i = 0; i < captured_frames * 2; i += 8)
        {
          printf("PCM %06x", i);
          for (unsigned j = i; j < i + 8 && j < captured_frames * 2; j++) printf(" %08" PRIx32, capture[j]);
          putchar('\n');
        }
      puts("SOUND_PCM_END");
      pthread_mutex_unlock(&owner);
      return 0;
    }
  bool probe = !strcmp(argv[1], "probe");
  playing = !strcmp(argv[1], "tone");
  bool recording = !strcmp(argv[1], "capture");
  if (recording) captured_frames = 0;
  unsigned frames = 3200;
  if (argc == 3)
    {
      char *end;
      unsigned long count = strtoul(argv[2], &end, 10);
      if (!recording || *end || count < 1 || count > 48000) goto invalid;
      frames = (unsigned)count;
    }
  if ((!probe && !playing && !recording) || bus.poisoned || bus.held || data_held || platform.held) goto invalid;
  struct saved_i2c old = {0};
  struct sap_port sap = {NULL, abs_read, abs_write, now_us};
  struct pio_result result = {0};
  struct kd_port kd = {NULL, now_ms, codec_write, codec_read, delay_ms, amplifier, codec_ready, quiesce};
  memset(&bus, 0, sizeof(bus));
  memset(&platform, 0, sizeof(platform));
  int rc = prepare_i2c(&old);
  if (!rc) rc = amp_prepare();
  old_audio_root = rd(NULL, CRU + 0x3a8);
  old_audio_gate = rd(NULL, CRU + 0x81c);
  bool clock_changed = false;
  if (!rc)
    {
      if (rd(NULL, CRU + 0xa20) & 0x60) rc = -EBUSY;
      else
        {
          /* All audio users are owned here. Choose HCLK xin24m, no PLL writes. */
          masked(CRU + 0x3a8, 3, 3);
          masked(CRU + 0x81c, 2, 0);
          clock_changed = true;
          if ((rd(NULL, CRU + 0x3a8) & 3) != 3 || (rd(NULL, CRU + 0x81c) & 2)) rc = -EIO;
        }
    }
  up_disable_irq(220);
  if (!rc) rc = sap_setup(&sap, &platform, 1);
  printf("SOUND platform_result=%d version=%08" PRIx32 " repair=%08" PRIx32
         " ack=%08" PRIx32 " idle=%08" PRIx32 "\n", rc, platform.version, platform.repair, platform.ack, platform.idle);
  if (!rc) rc = kd_bind(&codec, &kd);
  if (!rc) rc = kd_prepare(&codec, 32, now_ms(NULL) + 3000);
  printf("SOUND codec_prepare=%d state=%u\n", rc, codec.state);
  if (!rc && !probe)
    {
      struct pio_port pio = {NULL, sai_read, sai_write, now_us, arm_codec, enable_amp, amp_off, 1u << 27};
      rc = pio_run(&pio, 1, 4096000, playing, capture, 96000, frames, &result);
      data_held = result.held;
      if (recording) captured_frames = result.frames;
      printf("SOUND pio=%d frames=%u polls=%u stop=%d held=%d max_fifo=%u\n",
             rc, result.frames, result.polls, result.stop_result, result.held, result.max_fifo);
      if (recording && captured_frames)
        {
          struct pio_stats stats;
          pio_summarize(capture, captured_frames, &stats);
          printf("SOUND pcm left_min=%" PRId32 " left_max=%" PRId32 " left_nonzero=%u "
                 "right_min=%" PRId32 " right_max=%" PRId32 " right_nonzero=%u\n",
                 stats.min[0], stats.max[0], stats.nonzero[0], stats.min[1], stats.max[1], stats.nonzero[1]);
        }
    }
  int stop_rc = platform.ready ? kd_stop(&codec, now_ms(NULL) + 1500) : 0;
  if (amp_ready) amp_off(NULL);
  up_udelay(10);
  int platform_rc = platform.ready && !stop_rc && !data_held ? sap_cleanup(&sap, &platform, !quiesce(NULL, now_ms(NULL) + 10)) : (platform.held ? -EBUSY : 0);
  if (clock_changed && !platform.held)
    {
      masked(CRU + 0x3a8, 3, old_audio_root);
      masked(CRU + 0x81c, 2, old_audio_gate);
    }
  int bus_rc = !platform.held ? restore_i2c(&old) : -EBUSY;
  if (bus_rc) bus.poisoned = true;
  printf("SOUND result=%d codec_stop=%d platform_restore=%d i2c_restore=%d amp_low=%u\n",
         rc, stop_rc, platform_rc, bus_rc, amp_ready && !(rd(NULL, GPIO2) & 0x200));
  pthread_mutex_unlock(&owner);
  return rc || stop_rc || platform_rc || bus_rc ? 1 : 0;
invalid:
  puts("SOUND invalid_request_or_latched_fault");
  pthread_mutex_unlock(&owner);
  return 1;
}
