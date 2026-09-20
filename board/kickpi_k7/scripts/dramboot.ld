/****************************************************************************
 * boards/arm64/rk3576/kickpi_k7/scripts/dramboot.ld
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.  The
 * ASF licenses this file to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance with the
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

#include <nuttx/config.h>

OUTPUT_ARCH(aarch64)
ENTRY(__start)

MEMORY
{
  dram (rwx) : ORIGIN = CONFIG_RAM_START, LENGTH = CONFIG_RAM_SIZE
}

PHDRS
{
  text PT_LOAD FLAGS(5);
  rodata PT_LOAD FLAGS(4);
  data PT_LOAD FLAGS(6);
}

SECTIONS
{
  . = ORIGIN(dram);
  _start = .;
  .text : {
    _stext = .;
    KEEP(*(.start .start.*))
    *(.text .text.*)
    *(.fixup .gnu.warning)
  } > dram :text

  .init_section ALIGN(4096) : {
    _sinit = ABSOLUTE(.);
    /* Runtime registration must precede every C++ initializer. */
    KEEP(*(.k7_unwind_init))
    KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*) SORT_BY_INIT_PRIORITY(.ctors.*)))
    KEEP(*(.init_array EXCLUDE_FILE(*crtbegin.o *crtbegin?.o *crtend.o *crtend?.o) .ctors))
    _einit = ABSOLUTE(.);
  } > dram :text

  .vector ALIGN(4096) : {
    _vector_start = .;
    KEEP(*(.exc_vector_table .exc_vector_table.* .vectors))
    _vector_end = .;
    . = ALIGN(4096);
    _etext = .;
  } > dram :text
  _sztext = _etext - _stext;

  .rodata ALIGN(4096) : {
    _srodata = .;
    KEEP(*(.note.gnu.build-id))
    *(.note.gnu.property)
    *(.rodata .rodata.* .data.rel.ro .data.rel.ro.*)
  } > dram :rodata

  .eh_frame ALIGN(8) : {
    __k7_eh_frame_start = .;
    KEEP(*(.eh_frame .eh_frame.*))
    /* libgcc walks until a zero-length record, not an end pointer. */
    LONG(0)
    __k7_eh_frame_end = .;
  } > dram :rodata

  .gcc_except_table ALIGN(8) : {
    __k7_lsda_start = .;
    KEEP(*(.gcc_except_table .gcc_except_table.*))
    __k7_lsda_end = .;
    . = ALIGN(4096);
    _erodata = .;
  } > dram :rodata
  _szrodata = _erodata - _srodata;
  _eronly = .;

  .data ALIGN(4096) : {
    _sdata = .;
    *(.data.page_aligned)
    *(.data .data.*)
    . = ALIGN(8);
    CONSTRUCTORS
    _edata = .;
  } > dram :data

  .bss (NOLOAD) : {
    . = ALIGN(16);
    _sbss = .;
    *(.bss .bss.* COMMON)
    . = ALIGN(4096);
    _ebss = .;
  } > dram :data
  _szbss = _ebss - _sbss;

  .initstack ALIGN(4096) (NOLOAD) : {
    _s_initstack = .;
    *(.initstack .initstack.*)
    . = ALIGN(4096);
    _e_initstack = .;
    g_idle_topstack = .;
  } > dram :data
  _szdata = _e_initstack - _sdata;

  /DISCARD/ : {
    *(.exit.text .exit.data .exitcall.exit)
  }

  .stab 0 : { *(.stab) }
  .stabstr 0 : { *(.stabstr) }
  .stab.excl 0 : { *(.stab.excl) }
  .stab.exclstr 0 : { *(.stab.exclstr) }
  .stab.index 0 : { *(.stab.index) }
  .stab.indexstr 0 : { *(.stab.indexstr) }
  .comment 0 : { *(.comment) }
}

/* The captured K7 usable low DRAM bank is [0x40200000, 0x48400000).
 * Keep the initial image/heap inside it.  Do not assume contiguous RAM
 * across the firmware carve-out starting at 0x48400000.
 */

ASSERT(__start == ORIGIN(dram), "Image entry must equal RAM_START")
ASSERT(((ORIGIN(dram) - CONFIG_ARM64_IMAGE_TEXT_OFFSET) & 0x1fffff) == 0,
       "booti would relocate this fixed-address image")
ASSERT(ORIGIN(dram) >= 0x40200000 &&
       ORIGIN(dram) + LENGTH(dram) <= 0x48400000,
       "Configured RAM exceeds the captured K7 low DRAM bank")
ASSERT(_e_initstack < ORIGIN(dram) + LENGTH(dram), "No space left for heap")
