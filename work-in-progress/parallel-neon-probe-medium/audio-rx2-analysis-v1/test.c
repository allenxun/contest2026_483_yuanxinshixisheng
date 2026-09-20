#include <stdint.h>
#include <assert.h>
#include <stdio.h>
int rx2_pair_ready(uint32_t);
int main(void)
{
 assert(rx2_pair_ready(0)==0);
 assert(rx2_pair_ready(0x41)==0); /* original total2, each bank only1 */
 assert(rx2_pair_ready(0x40)==0); /* observed unchanged index1 */
 assert(rx2_pair_ready(0x42)==0);assert(rx2_pair_ready(0x81)==0);
 assert(rx2_pair_ready(0x82)==1);assert(rx2_pair_ready(0x102)==1);
 assert(rx2_pair_ready(33)==-1);assert(rx2_pair_ready(0x1000)==-1);
 assert(rx2_pair_ready(0x40000)==-1);
 puts("PASS pure RX2 readiness: total>=2 is insufficient; both observed banks require>=2");
 puts("Not proof of hardware bank cursor; no register write or sample filtering");
 return 0;
}
