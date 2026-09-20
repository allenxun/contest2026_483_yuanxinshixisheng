/****************************************************************************
 * arch/arm64/include/rk3576/chip.h
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

#ifndef __ARCH_ARM64_INCLUDE_RK3576_CHIP_H
#define __ARCH_ARM64_INCLUDE_RK3576_CHIP_H

#include <nuttx/config.h>

/* The initial port runs on A53 CPU0 (MPIDR affinity 0).  The remaining
 * cores stay parked in the boot firmware.  Cluster/coherency bring-up and
 * per-CPU stacks must be implemented before enabling SMP or BMP.
 */

#if !defined(CONFIG_BUILD_FLAT)
#  error "RK3576 requires a flat build"
#endif
#if !defined(CONFIG_UP)
#  if !defined(CONFIG_RK3576_SMP_DIAG) || !defined(CONFIG_SMP) || (CONFIG_SMP_NCPUS != 2 && CONFIG_SMP_NCPUS != 4 && CONFIG_SMP_NCPUS != 5 && CONFIG_SMP_NCPUS != 8)
#    error "RK3576 SMP is limited to the explicit explicit 2/4/5/8-core diagnostic profiles"
#  endif
#endif

#if CONFIG_ARM64_GIC_VERSION != 2
#  error "RK3576 uses the GIC-400 (GICv2)"
#endif

/* arm64_gicv2.c uses CONFIG_GICR_BASE for the GIC CPU interface.
 * This is GICC, not a GICv3 redistributor.
 */

#define CONFIG_GICD_BASE          0x2a701000
#define CONFIG_GICR_BASE          0x2a702000

/* Map the configured DRAM only.  Board RAM limits exclude secure firmware
 * and the gap in the captured K7 memory map.  Device mappings cover UART0
 * and GIC, with no overlap with DRAM.
 */

#define CONFIG_DEVICEIO_BASEADDR  0x2a000000
#define CONFIG_DEVICEIO_SIZE      0x02000000

#ifdef __ASSEMBLY__

/* Keep Aff1 as well as Aff0: A72 CPU0 (0x100) is not the boot CPU. */

.macro get_cpu_id xreg0
  mrs \xreg0, mpidr_el1
#ifdef CONFIG_RK3576_SMP_DIAG
  tbnz \xreg0, #16, .Lk7_cpu_park\@
  tbnz \xreg0, #17, .Lk7_cpu_park\@
  tbnz \xreg0, #18, .Lk7_cpu_park\@
  tbnz \xreg0, #19, .Lk7_cpu_park\@
  tbnz \xreg0, #20, .Lk7_cpu_park\@
  tbnz \xreg0, #21, .Lk7_cpu_park\@
  tbnz \xreg0, #22, .Lk7_cpu_park\@
  tbnz \xreg0, #23, .Lk7_cpu_park\@
  tbnz \xreg0, #32, .Lk7_cpu_park\@
  tbnz \xreg0, #33, .Lk7_cpu_park\@
  tbnz \xreg0, #34, .Lk7_cpu_park\@
  tbnz \xreg0, #35, .Lk7_cpu_park\@
  tbnz \xreg0, #36, .Lk7_cpu_park\@
  tbnz \xreg0, #37, .Lk7_cpu_park\@
  tbnz \xreg0, #38, .Lk7_cpu_park\@
  tbnz \xreg0, #39, .Lk7_cpu_park\@
  ubfx \xreg0, \xreg0, #0, #16
  cmp \xreg0, #4
  b.lo .Lk7_cpu_mapped\@
  cmp \xreg0, #0x100
  b.lo .Lk7_cpu_park\@
  cmp \xreg0, #0x104
  b.hs .Lk7_cpu_park\@
  sub \xreg0, \xreg0, #0xfc
.Lk7_cpu_mapped\@:
  cmp \xreg0, #CONFIG_SMP_NCPUS
  b.lo .Lk7_cpu_valid\@
.Lk7_cpu_park\@:
  wfe
  b .Lk7_cpu_park\@
.Lk7_cpu_valid\@:
#else
  ubfx \xreg0, \xreg0, #0, #16
#endif
.endm

#endif /* __ASSEMBLY__ */
#endif /* __ARCH_ARM64_INCLUDE_RK3576_CHIP_H */
