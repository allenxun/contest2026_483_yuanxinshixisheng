/****************************************************************************
 * arch/arm64/src/rk3576/rk3576_boot.c
 *
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to you under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with the
 * License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
 * License for the specific language governing permissions and limitations
 * under the License.
 *
 ****************************************************************************/

/****************************************************************************
 * Included Files
 ****************************************************************************/

#include <nuttx/config.h>

#include <stdint.h>
#include <assert.h>
#include <debug.h>

#include <nuttx/cache.h>
#ifdef CONFIG_LEGACY_PAGING
#  include <nuttx/page.h>
#endif

#include <arch/chip/chip.h>
#ifdef CONFIG_RK3576_SMP_DIAG
#include <arch/chip/rk3576_cpu_topology.h>
#endif

#ifdef CONFIG_SMP
#include "arm64_smp.h"
#endif

#include "arm64_arch.h"
#include "arm64_internal.h"
#include "arm64_mmu.h"
#include "rk3576_boot.h"
#ifdef CONFIG_RK3576_MODEL_ARENA
#include <nuttx/mm/k7_model_arena.h>
#endif

/****************************************************************************
 * Private Data
 ****************************************************************************/

#ifdef CONFIG_RK3576_UART6
int rk3576_uart6_initialize(void);
#endif

static const struct arm_mmu_region g_mmu_regions[] =
{
  MMU_REGION_FLAT_ENTRY("DEVICE_REGION",
                        CONFIG_DEVICEIO_BASEADDR, CONFIG_DEVICEIO_SIZE,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),

#if defined(CONFIG_RK3576_UART6) || defined(CONFIG_RK3576_USB_DIAG) || defined(CONFIG_EXAMPLES_K7EMMC)
  MMU_REGION_FLAT_ENTRY("RK3576_IOC", 0x26040000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_CRU", 0x27200000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

#ifdef CONFIG_RK3576_USB_DIAG
  MMU_REGION_FLAT_ENTRY("RK3576_USB_GRF", 0x2601e000, 0x1000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_USB_OTG", 0x23000000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_USB_HOST", 0x23400000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_PMU", 0x27380000, 0x1000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

#ifdef CONFIG_RK3576_USBHOST
  MMU_REGION_FLAT_ENTRY("RK3576_COMBOPHY1_GRF", 0x2602a000, 0x2000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_PHP_GRF", 0x26020000, 0x1000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_USB2PHY", 0x2602e000, 0x4000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_PMU_CRU", 0x27220000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

#ifdef CONFIG_RK3576_NPU_DIAG
  MMU_REGION_FLAT_ENTRY("RK3576_NPU", 0x27700000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

#ifdef CONFIG_EXAMPLES_K7RADIO
  /* Temporary radio firmware staged by the Windows UART loader, never heap.
   * The image and original 126 MiB heap end below 0x48200000.
   */
  MMU_REGION_FLAT_ENTRY("K7_RADIO_FW_INPUT", 0x50000000, 0x200000,
                        MT_RODATA | MT_SECURE),
#endif

#ifdef CONFIG_RK3576_MODEL_ARENA
  MMU_REGION_FLAT_ENTRY("K7_MODEL_ARENA", K7_MODEL_ARENA_BASE,
                        K7_MODEL_ARENA_SIZE, MT_NORMAL | MT_RW | MT_SECURE),
#endif

#ifdef CONFIG_EXAMPLES_K7EMMC
  MMU_REGION_FLAT_ENTRY("K7_EMMC", 0x2a330000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

  MMU_REGION_FLAT_ENTRY("DRAM0_S0",
                        CONFIG_RAM_START, CONFIG_RAM_SIZE,
                        MT_NORMAL | MT_RW | MT_SECURE),
};

const struct arm_mmu_config g_mmu_config =
{
  .num_regions = nitems(g_mmu_regions),
  .mmu_regions = g_mmu_regions,
};

/****************************************************************************
 * Public Functions
 ****************************************************************************/

#ifdef CONFIG_ARCH_EARLY_PRINT
static void rk3576_boot_putreg(const char *name, uint64_t value)
{
  static const char hex[] = "0123456789abcdef";
  int shift;

  while (*name != '\0')
    {
      arm64_lowputc(*name++);
    }

  for (shift = 60; shift >= 0; shift -= 4)
    {
      arm64_lowputc(hex[(value >> shift) & 15]);
    }

  arm64_lowputc('\r');
  arm64_lowputc('\n');
}
#endif

/****************************************************************************
 * Name: arm64_el_init
 *
 * Description:
 *   The function called from arm64_head.S at very early stage for these
 *   platform, it's use to:
 *   - Handling special hardware initialize routine which are need to
 *     run at high ELs
 *   - Initialize system software such as hypervisor or security firmware
 *     which are need to run at high ELs
 *
 ****************************************************************************/

void arm64_el_init(void)
{
  /* The Rockchip DDR loader, TF-A and U-Boot initialize DRAM,
   * clocks, pinmux and UART0 before entering this image.
   */

  if (read_sysreg(CurrentEL) == 8)
    {
#ifdef CONFIG_ARCH_EARLY_PRINT
      rk3576_boot_putreg("RK3576 HCR_EL2=", read_sysreg(hcr_el2));
      rk3576_boot_putreg("RK3576 SCTLR_EL1=", read_sysreg(sctlr_el1));
#endif

      /* The K7 U-Boot hands over HCR_EL2=0x08000032, including TGE.
       * TGE makes an ERET to EL1 illegal.  Establish a bare-metal AArch64
       * EL1 context without inherited traps or stage-2 translation.
       * Keep the EL1 MMU off until our own tables are installed.
       */

      write_sysreg(HCR_RW_BIT, hcr_el2);
      write_sysreg(SCTLR_EL1_RES1, sctlr_el1);
      UP_ISB();
    }
}

/****************************************************************************
 * Name: arm64_chip_boot
 *
 * Description:
 *   Complete boot operations started in arm64_head.S
 *
 ****************************************************************************/

void arm64_chip_boot(void)
{
  /* MAP IO and DRAM, enable MMU. */

  arm64_mmu_init(true);

  _info("RK3576: MMU enabled\n");

#if defined(CONFIG_ARM64_PSCI)
  arm64_psci_init("smc");
#endif

  /* Perform board-specific device initialization. This would include
   * configuration of board specific resources such as GPIOs, LEDs, etc.
   */

  rk3576_board_initialize();

#ifdef CONFIG_RK3576_UART6
  /* Do not expose a control port with unverified clock/pinmux settings. */
  if (rk3576_uart6_initialize() < 0)
    {
      _err("RK3576 UART6 initialization failed\n");
      PANIC();
    }
#endif

#ifdef USE_EARLYSERIALINIT
  /* Perform early serial initialization if we are going to use the serial
   * driver.
   */

  arm64_earlyserialinit();
#endif
}

#if defined(CONFIG_NET) && !defined(CONFIG_NETDEV_LATEINIT)
void arm64_netinitialize(void)
{
  /* TODO: Support net initialize */
}
#endif

#ifdef CONFIG_RK3576_SMP_DIAG
uint64_t arm64_get_mpid(int cpu)
{
  uint64_t affinity;
  if (cpu < 0 || vv_k7_cpu_affinity((unsigned)cpu, CONFIG_SMP_NCPUS, &affinity) < 0)
    {
      PANIC();
      return UINT64_MAX;
    }
  return affinity;
}

int arm64_get_cpuid(uint64_t mpid)
{
  return vv_k7_logical_cpu(mpid, CONFIG_SMP_NCPUS);
}
#endif
