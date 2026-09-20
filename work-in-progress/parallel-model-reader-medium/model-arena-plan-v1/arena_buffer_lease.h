#ifndef ARENA_BUFFER_LEASE_H
#define ARENA_BUFFER_LEASE_H
#include "ggml-backend.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Ownership proof helper, NOT a llama-selectable buft. External serialization.
 * alloc/release must form a trusted matching pair. Source ctx and storage must
 * outlive lease. Never copy lease. Only close after all tensor users quiesce. */
struct arena_source { void *ctx; void *(*alloc)(void *,size_t); void (*release)(void *,void *); };
struct arena_lease { void *memory; ggml_backend_buffer_t view; struct arena_source source; };
#define ARENA_LEASE_INIT { NULL, NULL, { NULL, NULL, NULL } }
int arena_lease_open(struct arena_lease *,struct arena_source,size_t bytes,size_t budget);
void arena_lease_close(struct arena_lease *);
#ifdef __cplusplus
}
#endif
#endif
