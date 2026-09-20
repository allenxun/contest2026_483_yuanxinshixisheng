#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#define FAR
typedef uint64_t libc_data_t;
#define LITTLEBLOCKSIZE 8
#undef UNALIGNED
#define UNALIGNED(s,x) ((uintptr_t)(s)&7)
#define TOO_SMALL(n) ((n)<8)
FAR void *tested_memset(FAR void *m, int c, size_t n)
{
  FAR libc_data_t *aligned_addr;
  FAR char *s = (FAR char *)m;
  libc_data_t buffer;
  int i;

  /* To avoid sign extension, copy C to an unsigned variable.  */

  while (UNALIGNED(s, 0))
    {
      if (n--)
        {
          *s++ = c;
        }
      else
        {
          return m;
        }
    }

  if (!TOO_SMALL(n))
    {
      /* If we get this far, we know that n is large and s is word-aligned. */

      aligned_addr = (FAR libc_data_t *)s;
      buffer = (unsigned char)c;
      buffer |= buffer << 8;
      buffer |= (buffer << 16);
      for (i = 32; i < LITTLEBLOCKSIZE * 8; i <<= 1)
        {
          buffer = (buffer << i) | buffer;
        }

      /* Unroll the loop.  */

      while (n >= LITTLEBLOCKSIZE * 4)
        {
          *aligned_addr++ = buffer;
          *aligned_addr++ = buffer;
          *aligned_addr++ = buffer;
          *aligned_addr++ = buffer;
          n -= 4 * LITTLEBLOCKSIZE;
        }

      while (n >= LITTLEBLOCKSIZE)
        {
          *aligned_addr++ = buffer;
          n -= LITTLEBLOCKSIZE;
        }

      /* Pick up the remainder with a bytewise loop.  */

      s = (FAR char *)aligned_addr;
    }

  while (n--)
    {
      *s++ = c;
    }

  return m;
}

int main(void) { unsigned char b[160]; int vals[]={-128,-1,0,128,255,256,384,0x1234}; unsigned failures=0, cases=0;
for(unsigned v=0;v<sizeof(vals)/sizeof(vals[0]);v++)for(unsigned off=0;off<8;off++)for(unsigned n=0;n<=96;n++){
 for(unsigned i=0;i<160;i++) b[i]=0x5a;
 if(tested_memset(b+16+off,vals[v],n)!=b+16+off)return 2;
 for(unsigned i=0;i<160;i++){unsigned char expected=(i>=16+off&&i<16+off+n)?(unsigned char)vals[v]:0x5a;if(b[i]!=expected){failures++;break;}}cases++;
}printf("cases=%u failures=%u\n",cases,failures);return failures?1:0;}
