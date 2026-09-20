#ifndef K7_MODEL_BUFFER_LOADER_H
#define K7_MODEL_BUFFER_LOADER_H
#include "model_reader.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Consumes opened, including on error. No reopen, allocation or Session creation.
 * dst is caller-owned exclusive storage, valid for capacity bytes. It must not
 * alias opened, expected or verified_size. Caller discards dst on every error.
 * Only verified_size > 0 permits Session creation; keep dst alive until Session
 * destruction. cancel is checked between bounded chunks, not inside driver I/O.
 * Caller must use the reader's trusted regular-file mount policy. */
int k7_model_fill_verified(mr_file *opened, void *dst, size_t capacity,
                          uint64_t expected_length,
                          const unsigned char expected[32],
                          int (*cancel)(void *), void *context,
                          size_t *verified_size);
#ifdef __cplusplus
}
#endif
#endif
