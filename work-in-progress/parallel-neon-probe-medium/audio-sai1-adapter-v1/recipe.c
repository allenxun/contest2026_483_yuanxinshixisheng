/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Offline recipe only. No MMIO, DMA, power, codec or hardware-ready API. */
#include <stdint.h>
#include <stddef.h>
#define BIT(n) (UINT32_C(1) << (n))
#define GENMASK(h,l) ((UINT32_MAX >> (31-(h))) & (UINT32_MAX << (l)))
#include "input/rockchip_sai.h"
#include "recipe.h"

int sai_recipe(uint32_t mclk_hz, struct sai_recipe *out)
{
  struct sai_recipe r = {0};
  uint32_t div;
  if (!out || !mclk_hz || mclk_hz % 512000u) return -1;
  div = mclk_hz / 512000u;
  if (!div || div > 4096u) return -1;
  r.item[0] = (struct sai_mask){SAI_RXCR,
    SAI_XCR_VDW_MASK | SAI_XCR_CSR_MASK | SAI_XCR_SNB_MASK |
    SAI_XCR_SBW_MASK | SAI_XCR_VDJ_MASK | SAI_XCR_EDGE_SHIFT_MASK,
    SAI_XCR_VDW(16) | SAI_XCR_CSR(1) | SAI_XCR_SNB(2) |
    SAI_XCR_SBW(16) | SAI_XCR_VDJ_L | SAI_XCR_EDGE_SHIFT_1};
  r.item[1] = (struct sai_mask){SAI_RX_SHIFT, SAI_XSHIFT_RIGHT_MASK,
    SAI_XSHIFT_RIGHT(2)};
  r.item[2] = (struct sai_mask){SAI_FSCR,
    SAI_FSCR_FW_MASK | SAI_FSCR_FPW_MASK | SAI_FSCR_EDGE_MASK,
    SAI_FSCR_FW(32) | SAI_FSCR_FPW(16) | SAI_FSCR_EDGE_DUAL};
  r.item[3] = (struct sai_mask){SAI_CKR, SAI_CKR_MDIV_MASK,
    SAI_CKR_MDIV(div)};
  r.item[4] = (struct sai_mask){SAI_DMACR, SAI_DMACR_RDL_MASK,
    SAI_DMACR_RDL(16)};
  r.rxdr_offset = SAI_RXDR;
  r.dma_bus_bytes = 4; r.dma_maxburst = 8;
  r.rate = 16000; r.bclk = 512000;
  *out = r;
  return 0;
}
