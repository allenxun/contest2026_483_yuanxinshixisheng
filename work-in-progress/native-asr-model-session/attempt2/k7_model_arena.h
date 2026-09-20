/* SPDX-License-Identifier: Apache-2.0 */
#ifndef __INCLUDE_NUTTX_MM_K7_MODEL_ARENA_H
#define __INCLUDE_NUTTX_MM_K7_MODEL_ARENA_H
#include <stddef.h>
#include <stdint.h>
#define K7_MODEL_ARENA_BASE UINT64_C(0x60000000)
#define K7_MODEL_ARENA_SIZE UINT64_C(0x40000000)
#ifdef __cplusplus
extern "C" {
#endif
/* CPU-only explicit arena. Not part of malloc(), USB or NPU DMA allocation. */
int k7_model_arena_initialize(void);
void *k7_model_alloc(size_t bytes);
void k7_model_free(void *memory);
size_t k7_model_available(void);
#ifdef __cplusplus
}
#endif
#endif
