/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef K7_SAI_RECIPE_H
#define K7_SAI_RECIPE_H
#include <stdint.h>
struct sai_mask { uint32_t offset, mask, value; };
struct sai_recipe {
  struct sai_mask item[5];
  uint32_t rxdr_offset, dma_bus_bytes, dma_maxburst, rate, bclk;
};
/* Successful output is an INCOMPLETE OFFLINE RECIPE, never hardware readiness.
 * Fixed I2S, 16kHz, 2x16bit, one lane, fw_ratio=1, SAI master assumption.
 * Excludes role/polarity/path/clock gates/reset/power/MMU/DMA/codec/start.
 * mclk_hz must be an independently verified actual clock, not a requested rate.
 * Invalid input leaves output unchanged. */
int sai_recipe(uint32_t mclk_hz, struct sai_recipe *out);
#endif
