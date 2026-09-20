/* Standalone candidate checks. Not yet integrated into usbhost_storage.c. */
#ifndef K7_MSC_READ_CHECKS_H
#define K7_MSC_READ_CHECKS_H
#include <stdint.h>
#include <stddef.h>
#include <errno.h>

/* Pass READ CAPACITY10 fields BEFORE narrowing or adding one. */
static inline int k7msc_capacity10_check(uint32_t last_lba, uint32_t blocksize)
{
  if (last_lba == UINT32_MAX) return -EOVERFLOW; /* READ CAPACITY16 needed */
  if (blocksize != 512 && blocksize != 1024 && blocksize != 2048 && blocksize != 4096)
    return -EINVAL;
  return 0;
}

/* Initial-read policy caps each transaction to 4 KiB, not a hardware limit. */
static inline int k7msc_read10_check(uint64_t blocks, uint32_t blocksize,
                                    int64_t lba, uint32_t count)
{
  if (!blocks || blocks > UINT32_MAX ||
      k7msc_capacity10_check((uint32_t)(blocks - 1), blocksize)) return -EINVAL;
  if (lba < 0 || (uint64_t)lba >= blocks || (uint64_t)lba > UINT32_MAX ||
      !count || count > UINT16_MAX || count > blocks - (uint64_t)lba) return -EINVAL;
  if (count > 4096 / blocksize) return -E2BIG;
  return 0;
}

static inline uint32_t k7msc_le32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Invoke only after separately checking exact CBW/data byte counts.
 * A short CSW is rejected before reading any fields; signed nbytes retains
 * negative transport failures. Nonzero status/residue requires BOT recovery. */
static inline int k7msc_csw_check(const uint8_t *csw, ptrdiff_t nbytes, uint32_t tag)
{
  if (!csw || nbytes != 13) return -EIO;
  if (k7msc_le32(csw) != UINT32_C(0x53425355) || k7msc_le32(csw + 4) != tag ||
      k7msc_le32(csw + 8) != 0 || csw[12] != 0) return -EIO;
  return 0;
}
#endif
