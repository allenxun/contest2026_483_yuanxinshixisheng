#include "model_buffer_loader.h"
#include "sha256_namespace.h"
#include <errno.h>
#include <stdint.h>

int k7_model_fill_verified(mr_file *opened, void *dst, size_t capacity,
                          uint64_t length, const unsigned char expected[32],
                          int (*cancel)(void *), void *context,
                          size_t *verified_size)
{
  mr_file file = MR_FILE_INIT;
  const mr_file empty = MR_FILE_INIT;
  sha256_t hash;
  unsigned char actual[32];
  size_t offset = 0;
  size_t chunk_limit;
  unsigned difference = 0;
  int error = EINVAL;
  int close_error;
  if (verified_size) *verified_size = 0;
  if (!opened) return EINVAL;
  file = *opened;
  *opened = empty;
  if (file.fd < 0) return EBADF;
  if (!verified_size || !dst || !expected || !length ||
      length > SIZE_MAX || length > UINT64_MAX / 8 || length > capacity ||
      length != file.length || !file.max_read) goto close;
  chunk_limit = file.max_read < 4096 ? (size_t)file.max_read : 4096;
  if (cancel && cancel(context)) { error = ECANCELED; goto close; }
  error = mr_seek(&file, 0);
  if (error) goto close;
  while (offset < (size_t)length)
    {
      size_t amount = (size_t)length - offset;
      if (amount > chunk_limit) amount = chunk_limit;
      if (cancel && cancel(context)) { error = ECANCELED; goto close; }
      error = mr_read_exact(&file, (unsigned char *)dst + offset, amount);
      if (error) goto close;
      offset += amount;
    }
  /* Hash precisely the retained destination, without another file read. */
  sha256_init(&hash);
  for (offset = 0; offset < (size_t)length; )
    {
      size_t amount = (size_t)length - offset;
      if (amount > chunk_limit) amount = chunk_limit;
      if (cancel && cancel(context)) { error = ECANCELED; goto close; }
      sha256_update(&hash, (const unsigned char *)dst + offset, amount);
      offset += amount;
    }
  sha256_final(&hash, actual);
  for (offset = 0; offset < sizeof(actual); ++offset)
    difference |= actual[offset] ^ expected[offset];
  error = difference ? EILSEQ : 0;
close:
  close_error = file.fd >= 0 ? mr_close(&file) : file.close_error;
  if (!error) error = close_error;
  if (!error && cancel && cancel(context)) error = ECANCELED;
  if (!error) *verified_size = (size_t)length;
  return error;
}
