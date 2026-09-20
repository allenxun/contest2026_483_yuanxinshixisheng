#ifndef KA_RK3X_REGISTERS_H
#define KA_RK3X_REGISTERS_H
#include "adapter.h"
/* Register backend candidate. ready means external clock/divider/tuning,
 * M0 pinmux/rails and single bus ownership established; no boot writes here.
 * Access callbacks must provide device MMIO barriers and never block. */
struct ka_rk3x {
 void *ctx;
 uint32_t (*read32)(void *,uintptr_t);
 void (*write32)(void *,uintptr_t,uint32_t);
 int (*lines_idle)(void *);
 bool ready,active,reading,stopping;
 uint32_t tuning;
};
int ka_rk_begin(void *,bool,uint8_t,uint8_t,uint8_t);
int ka_rk_poll(void *,size_t *,size_t *,uint8_t *);
int ka_rk_stop(void *);
int ka_rk_idle(void *);
#endif
