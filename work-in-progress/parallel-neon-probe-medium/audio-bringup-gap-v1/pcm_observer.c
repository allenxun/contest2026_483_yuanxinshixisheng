#include "pcm_observer.h"
#include <string.h>
#include <errno.h>
void po_init(struct po_stats *s){if(s)memset(s,0,sizeof(*s));}
int po_push(struct po_stats *s,const unsigned char *p,size_t bytes) {
 if(!s||!p||!bytes||bytes>PO_MAX_CHUNK||bytes%4)return EINVAL;
 if(s->frames>PO_MAX_FRAMES||bytes/4>PO_MAX_FRAMES-s->frames)return EOVERFLOW;
 for(size_t frame=0;frame<bytes/4;frame++) {
  for(unsigned ch=0;ch<2;ch++) {
   size_t i=frame*4+ch*2;
   uint32_t word=(uint32_t)p[i]|((uint32_t)p[i+1]<<8);
   int32_t value=word>=32768u?(int32_t)word-65536:(int32_t)word;
   struct po_channel *c=&s->channel[ch];
   if(!s->frames||value<c->min)c->min=value;
   if(!s->frames||value>c->max)c->max=value;
   c->sum+=value;c->sum_squares+=(uint64_t)((int64_t)value*value);
   uint32_t magnitude=(uint32_t)(value<0?-value:value);
   if(magnitude>c->peak)c->peak=magnitude;
   if(value==-32768||value==32767)c->clipped++;
   if(value)c->nonzero++;
  }
  s->frames++;
 }
 return 0;
}
int po_complete(const struct po_stats *s,uint32_t expected) {
 if(!s||!expected||expected>PO_MAX_FRAMES)return EINVAL;
 return s->frames==expected?0:EIO;
}
