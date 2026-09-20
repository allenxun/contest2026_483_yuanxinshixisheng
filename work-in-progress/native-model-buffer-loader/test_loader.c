#define MR_TESTING 1
#include "model_reader.c"
#include "model_buffer_loader.h"
#include "fixture_hash.h"
#include <assert.h>

static int calls, cancel_at;
static int cancelled(void *context)
{
  assert(context == &calls);
  return ++calls == cancel_at;
}
int main(int argc, char **argv)
{
  unsigned char buffer[8193], wrong[32] = {0};
  assert(argc == 2);
  for (int test = 0; test < 20; ++test)
    {
      mr_file f = MR_FILE_INIT;
      size_t verified = 123, capacity = sizeof(buffer);
      uint64_t length = sizeof(buffer);
      const unsigned char *digest = expected;
      int want = 0;
      memset(&fault, 0, sizeof(fault));
      calls = 0; cancel_at = 0;
      assert(mr_open(&f, argv[1], sizeof(buffer), sizeof(buffer), 4096) == 0);
      switch (test)
        {
          case 1: digest = wrong; want = EILSEQ; break;
          case 2: capacity--; want = EINVAL; break;
          case 3: length--; want = EINVAL; break;
          case 4: fault.seek_error = 1; want = EIO; break;
          case 5: fault.short_read = 1; break;
          case 6: fault.eintr = 3; break;
          case 7: fault.eintr = 17; want = EINTR; break;
          case 8: fault.read_error = 1; want = EIO; break;
          case 9: fault.eof = 1; want = EIO; break;
          case 10: fault.stat_error = 1; want = EIO; break;
          case 11: fault.close_error = 1; want = EIO; break;
          case 12: cancel_at = 1; want = ECANCELED; break;
          case 13: cancel_at = 3; want = ECANCELED; break;
          case 14: cancel_at = 6; want = ECANCELED; break;
          case 15: cancel_at = 8; want = ECANCELED; break;
          case 16: want = EINVAL; break;
          case 17: want = EINVAL; break;
          case 18: length = 0; want = EINVAL; break;
          case 19: f.max_read = 0; want = EINVAL; break;
        }
      int error = k7_model_fill_verified(&f, test == 17 ? NULL : buffer,
          capacity, length, digest, cancelled, &calls,
          test == 16 ? NULL : &verified);
      if (error != want) fprintf(stderr, "case %d got %d want %d\n", test, error, want);
      assert(error == want && f.fd == -1 && fault.closes == 1);
      if (test != 16) assert(verified == (want ? 0 : sizeof(buffer)));
      if (!want)
        for (size_t i = 0; i < sizeof(buffer); ++i)
          assert(buffer[i] == (unsigned char)(i * 37 + 11));
    }
  puts("PASS: 20 real-file model-buffer scenarios; injected faults are host-only");
  return 0;
}
