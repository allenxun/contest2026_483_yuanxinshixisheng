/****************************************************************************
 * arch/arm64/src/rk3576/rk3576_lowputc.S
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
 ****************************************************************************
 *
 *    DESCRIPTION
 *       Low-level console output for Rockchip RK3576 (DW APB UART,
 *       32-bit register access, reg-shift = 2)
 *
 ***************************************************************************/

#include <nuttx/config.h>

#include "arm64_macro.inc"

/****************************************************************************
 * Public Symbols
 ****************************************************************************/

    .file    "rk3576_lowputc.S"

/****************************************************************************
 * Assembly Macros
 ****************************************************************************/

/* Rockchip RK3576 UART0 Base Address */

#define UART0_BASE_ADDRESS CONFIG_16550_UART0_BASE

/* Register offsets (reg-shift = 2) */

#define UART_THR 0x00            /* Transmit Holding Register */
#define UART_LSR 0x14            /* Line Status Register */
#define UART_LSR_THRE 0x20       /* Transmit Holding Register Empty */

/****************************************************************************
 * Private Functions
 ****************************************************************************/

/* Wait for RK3576 UART to be ready to transmit
 * xb: Register that contains the UART Base Address
 * wt: Scratch register number
 */

.macro early_uart_ready xb, wt
1:
    ldr   \wt, [\xb, #UART_LSR]  /* UART_LSR (Line Status Register) */
    tst   \wt, #UART_LSR_THRE    /* Check THRE (TX Holding Register Empty) */
    b.eq  1b                     /* Wait for the UART to be ready */
.endm

/* Transmit character on RK3576 UART
 * xb: Register that contains the UART base address
 * wt: Register that contains the character to transmit
 */

.macro early_uart_transmit xb, wt
    str   \wt, [\xb, #UART_THR]  /* UART_THR (Transmit Holding Register) */
.endm

/****************************************************************************
 * Public Functions
 ****************************************************************************/

/* Print a character on the UART - this function is called from C
 * x0: Character to print
 */

GTEXT(arm64_lowputc)
SECTION_FUNC(text, arm64_lowputc)
    ldr   x15, =UART0_BASE_ADDRESS
    early_uart_ready x15, w2
    early_uart_transmit x15, w0
    ret
