#ifndef MODEL_INTEGRITY_H
#define MODEL_INTEGRITY_H
#include "input/formal/model_reader.h"
/* Fields are private by contract. Initialize once; do not copy or directly
 * use file. Externally serialize all calls; objects and buffers must not alias. */
typedef enum { MI_UNVERIFIED, MI_VERIFYING, MI_READY, MI_FAILED, MI_CLOSED } mi_state;
typedef struct { mr_file file; mi_state state; } mi_model;
#define MI_MODEL_INIT { MR_FILE_INIT, MI_UNVERIFIED }
#define MI_SCRATCH_MAX 4096u
/* Consumes the already-open handle (resets *opened); never reopens a path.
 * Success restores the original absolute position and only then sets READY.
 * Failure closes the consumed handle and leaves FAILED. Empty models rejected.
 * expected_sha256 must point to 32 trusted expected digest bytes.
 * scratch: caller-owned 1..4096 bytes, <= opened->max_read; contents unspecified.
 * This provides content verification, NOT immutability: require a trusted
 * immutable mount or external write exclusion through subsequent model use. */
int mi_verify_open(mi_model *, mr_file *opened, uint64_t expected_length,
                   const unsigned char expected_sha256[32], void *scratch, size_t scratch_size);
int mi_is_ready(const mi_model *);
int mi_read(mi_model *, void *, size_t);
int mi_seek(mi_model *, uint64_t);
int mi_close(mi_model *);
#endif
