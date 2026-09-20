#ifndef K7_I2C3_ADAPTER_H
#define K7_I2C3_ADAPTER_H
#include "codec_txn.h"
#include <stdbool.h>
#include <stdint.h>
#define KA_I2C3_BASE UINT32_C(0x2ac60000)
#define KA_CODEC_ADDRESS 0x10u
#define KA_POLL_LIMIT 4096u
/* No enabled direct MMIO port: board clock/timing/ownership unverified. */
struct ka_backend {
  void *ctx;
  uint64_t (*now_ms)(void *);
  int (*trylock)(void *); /* Same physical bus arbiter for every client. */
  void (*unlock)(void *);
  /* Copy values; must never retain a caller buffer. Nonblocking operations. */
  int (*begin)(void *,bool read,uint8_t address,uint8_t reg,uint8_t value);
  /* 0=pending, 1=complete, negative=error; exact per-direction byte counts. */
  int (*poll)(void *,size_t *tx,size_t *rx,uint8_t *value);
  int (*stop)(void *);
  int (*idle)(void *); /* 1=STOP completed AND controller/bus quiescent. */
};
struct ka_adapter {
  struct ka_backend backend;
  bool initialized,leased,poisoned;
  uint64_t last_time;
};
/* Must be zero-initialized, not copied or reinitialized while live. */
enum kc_status ka_init(struct ka_adapter *,const struct ka_backend *,enum kc_mode);
struct kc_io_result ka_write(void *,uint8_t,const uint8_t *,size_t,uint64_t);
struct kc_io_result ka_read(void *,uint8_t,uint8_t,uint8_t *,uint64_t);
/* Bus-only cleanup. MUST NOT masquerade as codec KC_QUIESCE (SAI/amp unknown). */
int ka_cleanup(struct ka_adapter *,uint64_t);
#endif
