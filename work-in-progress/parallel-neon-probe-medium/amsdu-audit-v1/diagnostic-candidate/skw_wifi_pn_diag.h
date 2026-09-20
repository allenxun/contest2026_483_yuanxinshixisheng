/* SPDX-License-Identifier: GPL-2.0-only */
/* Included after skw_amsdu_pending. Single RX owner only, no I/O or payload. */
#ifndef SKW_WIFI_PN_DIAG_H
#define SKW_WIFI_PN_DIAG_H
#include <limits.h>
#define SKW_PN_DIAG_CAPACITY 16
#define SKW_PN_DIAG_INTERVAL_MS 1000
enum skw_pn_reason { SKW_PN_FLOOR=1, SKW_PN_PENDING_NEWER,
                     SKW_PN_PENDING_TUPLE, SKW_PN_DUPLICATE_INDEX };
struct skw_pn_record {
  uint64_t now_ms,pn,floor,pending_pn,age_ms;
  uint16_t sequence,pending_sequence;
  uint8_t tid,index,bitmap,first_index,last_index,reason;
  bool multicast,amsdu,first,last,pending_active,last_seen,age_valid;
};
struct skw_pn_diag {
  struct skw_pn_record entries[SKW_PN_DIAG_CAPACITY];
  unsigned count,seen,suppressed,full;
  uint64_t last_ms;
  bool has_last;
};
static inline void skw_pn_sat(unsigned *n) {if(*n<UINT_MAX)(*n)++;}
static inline int skw_pn_reject(struct skw_pn_diag *d,enum skw_pn_reason reason,
 const struct skw_data_view *v,uint64_t floor,const struct skw_amsdu_pending *p,
 uint64_t now)
{
  if(!d)return -EACCES;
  skw_pn_sat(&d->seen);
  if(d->count>=SKW_PN_DIAG_CAPACITY){skw_pn_sat(&d->full);return -EACCES;}
  /* Backwards time cannot bypass rate limiting or underflow age. */
  if(d->has_last && (now<d->last_ms || now-d->last_ms<SKW_PN_DIAG_INTERVAL_MS))
    {skw_pn_sat(&d->suppressed);return -EACCES;}
  struct skw_pn_record *s=&d->entries[d->count++];
  memset(s,0,sizeof(*s));
  s->reason=(uint8_t)reason;s->now_ms=now;s->pn=v->pn;s->floor=floor;
  s->tid=v->tid;s->multicast=v->multicast;s->amsdu=v->amsdu;
  s->sequence=v->sequence;
  s->index=v->index+(reason==SKW_PN_DUPLICATE_INDEX?p->first_index:0);
  s->first=v->first;s->last=v->last;
  s->pending_active=p->active;
  if(p->active) {
    s->pending_pn=p->pn;s->pending_sequence=p->sequence;s->bitmap=p->bitmap;
    s->first_index=p->first_index;s->last_index=p->last_index;s->last_seen=p->last_seen;
    s->age_valid=now>=p->started_ms;
    if(s->age_valid)s->age_ms=now-p->started_ms;
  }
  d->has_last=true;d->last_ms=now;
  return -EACCES;
}
#endif
