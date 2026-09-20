#ifndef MODEL_READER_H
#define MODEL_READER_H
#include <stdint.h>
#include <stddef.h>
/* Initialize once. Noncopyable ownership by convention; externally serialize calls. */
typedef struct { int fd; uint64_t length, position, max_read; int close_error; } mr_file;
#define MR_FILE_INIT { -1, 0, 0, 0, 0 }
/* Returns 0 or a positive errno. All operation failures close the handle.
 * Caller must discard destination bytes on any failed read (partial writes possible).
 * expected_length is mandatory; max_length and max_read are caller budgets.
 * Only immutable files under a trusted directory may be used. */
int mr_open(mr_file *, const char *, uint64_t expected_length, uint64_t max_length, uint64_t max_read);
int mr_seek(mr_file *, uint64_t absolute_offset);
int mr_read_exact(mr_file *, void *, size_t);
int mr_close(mr_file *);
#endif
