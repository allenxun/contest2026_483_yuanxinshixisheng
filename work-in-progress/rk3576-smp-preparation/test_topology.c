#include "topology.h"
#include <assert.h>
#include <stdio.h>
#include <limits.h>

int main(void)
{
  static const uint64_t expected[] = {0,1,2,3,0x100,0x101,0x102,0x103};
  uint64_t out;
  unsigned count = 0;
  for (unsigned enabled=1; enabled<=8; enabled++)
    for (unsigned cpu=0; cpu<8; cpu++)
      {
        out = UINT64_MAX;
        int rc = vv_k7_cpu_affinity(cpu,enabled,&out);
        assert((rc==0) == (cpu<enabled));
        assert(out == (cpu<enabled ? expected[cpu] : UINT64_MAX));
        assert(vv_k7_logical_cpu(expected[cpu],enabled) ==
               (cpu<enabled ? (int)cpu : -1));
        assert(vv_k7_logical_cpu(expected[cpu] | UINT64_C(0x81000000),enabled)
               == (cpu<enabled ? (int)cpu : -1));
        count++;
      }
  /* Exhaust Aff0/Aff1: unexpected clusters/cores must never become indices. */
  for (unsigned a=0;a<65536;a++)
    {
      int valid = (a<4 || (a>=0x100 && a<=0x103));
      assert((vv_k7_logical_cpu(a,8)>=0)==valid);
      count++;
    }
  assert(vv_k7_logical_cpu(UINT64_C(0x10000),8)==-1);
  assert(vv_k7_logical_cpu(UINT64_C(0x100000000),8)==-1);
  assert(vv_k7_logical_cpu(0,0)==-1);
  assert(vv_k7_logical_cpu(0,9)==-1);
  assert(vv_k7_cpu_affinity(UINT_MAX,8,&out)==-1);
  assert(vv_k7_cpu_affinity(0,8,0)==-1);
  assert(vv_k7_cpu_affinity(0,0,&out)==-1);
  printf("PASS topology cases=%u plus invalid affinity/count/pointer boundaries\n",count);
  return 0;
}
