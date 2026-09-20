#ifndef LOOPBACK_RECIPE_H
#define LOOPBACK_RECIPE_H
#include <stdint.h>
/* Offline recipe only. No MMIO, no clocks/streams/codec activation. */
struct lb_snapshot {
 uint32_t version, xfer, dmacr, intcr, txfifo, rxfifo;
 uint32_t txcr, rxcr, fscr, ckr, mono, txshift, rxshift, path;
 int amp_low, common_clock_verified;
};
struct lb_recipe { uint32_t mask, saved, enabled; int valid; };
int lb_plan(const struct lb_snapshot *, struct lb_recipe *);
int lb_restore(const struct lb_recipe *, uint32_t current_path,
               int streams_idle, int amp_low, uint32_t *restored);
uint32_t lb_marker(unsigned word_index);
#endif
