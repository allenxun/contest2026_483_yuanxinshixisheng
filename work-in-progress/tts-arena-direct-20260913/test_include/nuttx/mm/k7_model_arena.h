#pragma once
#include <stddef.h>
#include <stdint.h>

#define K7_MODEL_ARENA_BASE UINT64_C(0x60000000)
#define K7_MODEL_ARENA_SIZE UINT64_C(0x20000000)

#ifdef __cplusplus
extern "C" {
#endif
int k7_model_arena_initialize(void);
void *k7_model_alloc(size_t bytes);
void k7_model_free(void *memory);
size_t k7_model_available(void);
#ifdef __cplusplus
}
#endif
