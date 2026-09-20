/****************************************************************************
 * arch/arm64/src/rk3576/rk3576_serial.c
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

#include <nuttx/serial/uart_16550.h>
#include "arm64_internal.h"

/* The generic driver multiplies REGINCR by sizeof(uart_datawidth_t).
 * REGINCR=1 and REGWIDTH=32 therefore give the required 4-byte stride.
 */

#if CONFIG_16550_REGINCR != 1 || CONFIG_16550_REGWIDTH != 32
#  error "RK3576 UART requires 32-bit MMIO with a 4-byte stride"
#endif

/****************************************************************************
 * Public Functions
 ****************************************************************************/

#ifdef USE_SERIALDRIVER

/****************************************************************************
 * Name: arm64_serialinit
 *
 * Description:
 *   See arm64_internal.h
 *
 ****************************************************************************/

void arm64_serialinit(void)
{
  u16550_serialinit();
}

/****************************************************************************
 * Name: arm64_earlyserialinit
 *
 * Description:
 *   See arm64_internal.h
 *
 ****************************************************************************/

void arm64_earlyserialinit(void)
{
  u16550_earlyserialinit();
}

#endif /* USE_SERIALDRIVER */
