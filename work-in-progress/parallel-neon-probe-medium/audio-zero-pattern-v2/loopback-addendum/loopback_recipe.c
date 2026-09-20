#include "loopback_recipe.h"
#include <stddef.h>
#include <string.h>
int lb_plan(const struct lb_snapshot *s, struct lb_recipe *r)
{
 if(!r)return -1;
 memset(r,0,sizeof(*r));
 if(!s)return -1;
 if(!s->amp_low || !s->common_clock_verified)return -2;
 if(s->version!=0x23073576u || s->xfer || s->dmacr ||
    (s->intcr&0x30003u) || s->txfifo || s->rxfifo)return -3;
 if(s->txcr!=0x00400fffu || s->rxcr!=0x00400fffu ||
    s->fscr!=0x0101f03fu || s->ckr!=0x18u || s->mono ||
    s->txshift!=2 || s->rxshift!=2 || (s->path&0x30000u))return -4;
 /* PATH [23:22] SDI0 source=SDO0, [21:18] only loop0 enabled,
  * [9:8] RX path0=SDI0, [1:0] SDO0=TX path0. */
 r->mask=0x00fc0303u;
 r->saved=s->path&r->mask;
 r->enabled=(s->path&~r->mask)|0x00040000u;
 r->valid=1;
 return 0;
}
int lb_restore(const struct lb_recipe *r,uint32_t current_path,
               int streams_idle,int amp_low,uint32_t *restored)
{
 if(!r || !r->valid || !restored)return -1;
 if(!streams_idle || !amp_low)return -2;
 *restored=(current_path&~r->mask)|r->saved;
 return 0;
}
uint32_t lb_marker(unsigned word_index)
{
 /* Eight distinct, low-amplitude, nonzero raw32 words. Sequence, NOT bank. */
 static const uint32_t pattern[8]={0x01012300u,0x02024500u,0x03036700u,
  0x04048900u,0x0505ab00u,0x0606cd00u,0x0707ef00u,0x08081100u};
 return pattern[word_index&7u];
}
