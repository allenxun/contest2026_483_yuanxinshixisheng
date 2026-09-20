#ifndef K7_CODEC_DUPLEX_H
#define K7_CODEC_DUPLEX_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
enum kd_state { KD_OFF, KD_CONFIGURING, KD_PREPARED, KD_ACTIVE, KD_FAULT };
/* All callbacks serialized and deadline-bounded. 0=success, negative errno=failure.
 * write: combined register/value TX2. read: repeated-start register TX1/RX1.
 * amp(false) must physically disable GPIO2_B1. quiesce must JOIN old DMA/I/O.
 * ready must confirm the actual clocks/slots and, for activation, running streams.
 * No callback may retain stack pointers or merely enqueue and return success. */
struct kd_port {
 void *arg;
 uint64_t (*now)(void *);
 int (*write)(void *,uint8_t address,uint8_t reg,uint8_t value,uint64_t deadline);
 int (*read)(void *,uint8_t address,uint8_t reg,uint8_t *value,uint64_t deadline);
 int (*delay)(void *,unsigned ms,uint64_t deadline);
 int (*amp)(void *,bool on,uint64_t deadline);
 int (*ready)(void *,unsigned word_bits,uint32_t mclk,uint32_t bclk,bool capture,bool playback,uint64_t deadline);
 int (*quiesce)(void *,uint64_t deadline);
};
struct kd_codec { struct kd_port io; enum kd_state state; uint64_t last; int error; bool busy; unsigned word_bits; };
int kd_bind(struct kd_codec *,const struct kd_port *);
/* word_bits=16 or32, stereo slots of the same width, fixed Fs16000/MCLK4096000. */
int kd_prepare(struct kd_codec *,unsigned word_bits,uint64_t deadline);
int kd_activate(struct kd_codec *,bool capture,bool playback,uint64_t deadline);
int kd_mute(struct kd_codec *,uint64_t deadline);
/* Keeps clocks available; root may disable clocks only after successful stop. */
int kd_stop(struct kd_codec *,uint64_t deadline);
#endif
