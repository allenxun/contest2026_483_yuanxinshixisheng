/* SPDX-License-Identifier: Apache-2.0 */
/* Fixed KICKPI-K7 UART6 M0 bring-up. Registers checked against Rockchip
 * develop-6.1 clk-rk3576.c, clk.h, rockchip,rk3576-cru.h and pinctrl.
 * The shared bus clocks, DDR and power domains remain bootloader supplied.
 */
#include <nuttx/config.h>
#include <nuttx/arch.h>
#include <stdint.h>
#include <errno.h>
#include <debug.h>
#include "arm64_arch.h"

#define UART6             0x2ad90000ul
#define CRU               0x27200000ul
#define CLKSEL65          (CRU + 0x404)
#define GATE13            (CRU + 0x834)
#define GATE15            (CRU + 0x83c)
#define RESET13           (CRU + 0xa34)
#define RESET15           (CRU + 0xa3c)
#define GPIO4A_MUX_H      0x26044084ul
#define GPIO4A_PULL       0x26046140ul
#define RBR_THR_DLL       (UART6 + 0x00)
#define IER_DLH           (UART6 + 0x04)
#define FCR               (UART6 + 0x08)
#define LCR               (UART6 + 0x0c)
#define MCR               (UART6 + 0x10)
#define LSR               (UART6 + 0x14)
#define USR               (UART6 + 0x7c)
#define SRR               (UART6 + 0x88)

static void masked(uintptr_t address, uint32_t mask, uint32_t value)
{
  /* Rockchip upper-half write-enable mask, never read/modify/write these. */
  putreg32((mask << 16) | (value & mask), address);
}

static int wait_lsr(uint32_t mask)
{
  for (unsigned int i = 0; i < 10000; i++)
    {
      if ((getreg32(LSR) & mask) == mask)
        {
          return 0;
        }
      up_udelay(1);
    }
  return -ETIMEDOUT;
}

int rk3576_uart6_initialize(void)
{
  static const uint8_t pattern[] = {0x55, 0xaa, 0x00, 0x0a, 0xff, 0xfa};

  /* Assert only UART6 APB/serial resets (IDs 223/242), enable its clocks,
   * and select xin24m / 1. No PLL or UART0 clock is changed.
   */
  masked(RESET13, 1u << 15, 1u << 15);
  masked(RESET15, 1u << 2, 1u << 2);
  masked(GATE13, 1u << 15, 0);
  masked(GATE15, 1u << 2, 0);
  masked(CLKSEL65, 0x7ff, 3u << 8);
  up_udelay(10);
  masked(RESET13, 1u << 15, 0);
  masked(RESET15, 1u << 2, 0);
  up_udelay(10);

  /* GPIO4_A4=TX / GPIO4_A6=RX, mux 10. PULL_TYPE_IO_1 pull-up is 3. */
  masked(GPIO4A_MUX_H, 0x0f0f, 0x0a0a);
  masked(GPIO4A_PULL, 0x3300, 0x3300);

  if ((getreg32(CLKSEL65) & 0x7ff) != 0x300 ||
      (getreg32(GPIO4A_MUX_H) & 0x0f0f) != 0x0a0a ||
      (getreg32(GATE13) & (1u << 15)) ||
      (getreg32(GATE15) & (1u << 2)))
    {
      _err("UART6 clock/pinmux readback failed\n");
      return -EIO;
    }

  putreg32(7, SRR);
  up_udelay(10);
  putreg32(0, IER_DLH);
  putreg32(0x83, LCR);
  if ((getreg32(LCR) & 0xff) != 0x83)
    {
      return -EIO;
    }
  /* 24 MHz / (16 * 13) = 115384.6 baud, +0.16% versus 115200. */
  putreg32(13, RBR_THR_DLL);
  putreg32(0, IER_DLH);
  if ((getreg32(RBR_THR_DLL) & 0xff) != 13 ||
      (getreg32(IER_DLH) & 0xff) != 0)
    {
      return -EIO;
    }
  putreg32(3, LCR);
  putreg32(7, FCR);

  /* Internal loopback holds TX at its idle level; test bytes do not go
   * to the MCU. This checks the peripheral, not pins/wiring/MCU reception.
   */
  putreg32(0x10, MCR);
  for (unsigned int i = 0; i < sizeof(pattern); i++)
    {
      if (wait_lsr(0x20) < 0)
        {
          putreg32(0, MCR);
          return -ETIMEDOUT;
        }
      putreg32(pattern[i], RBR_THR_DLL);
      if (wait_lsr(1) < 0 || (getreg32(RBR_THR_DLL) & 0xff) != pattern[i])
        {
          putreg32(0, MCR);
          return -EIO;
        }
    }
  if (wait_lsr(0x40) < 0)
    {
      putreg32(0, MCR);
      return -ETIMEDOUT;
    }
  putreg32(0, MCR);
  putreg32(7, FCR);
  putreg32(0, IER_DLH);
  (void)getreg32(USR);
  _info("UART6 M0: 115200 8N1, internal loopback PASS, IRQ114 ttyS1\n");
  return 0;
}
