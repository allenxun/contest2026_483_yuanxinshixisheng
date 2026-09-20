/****************************************************************************
 * arch/arm64/src/rk3576/rk3576_boot.h
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

#ifndef __ARCH_ARM64_SRC_RK3576_RK3576_BOOT_H
#define __ARCH_ARM64_SRC_RK3576_RK3576_BOOT_H

#ifndef __ASSEMBLY__
#ifdef __cplusplus
extern "C"
{
#endif

/* Called after the MMU has been initialized.  DRAM and debug UART must
 * already have been initialized by the bootloader.
 */

void rk3576_board_initialize(void);

#ifdef __cplusplus
}
#endif
#endif
#endif /* __ARCH_ARM64_SRC_RK3576_RK3576_BOOT_H */
