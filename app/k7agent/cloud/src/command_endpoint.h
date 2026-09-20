/* Bounded conservative speech endpoint; operates on complete 20ms PCM frames. */
#ifndef K7_COMMAND_ENDPOINT_H
#define K7_COMMAND_ENDPOINT_H
#include <stdint.h>
struct k7_command_endpoint {
  unsigned frames, voiced, quiet, last_active;
  uint32_t absolute_sum;
};
static inline int k7_endpoint_sample(struct k7_command_endpoint *s,int16_t sample)
{
  s->absolute_sum+=(uint32_t)(sample<0?-(int32_t)sample:sample);
  return 0;
}
static inline int k7_endpoint_frame(struct k7_command_endpoint *s)
{
  unsigned mean=s->absolute_sum/320u;s->absolute_sum=0;s->frames++;
  if(mean>=350)s->voiced++;
  if(mean>=200){s->quiet=0;s->last_active=s->frames;}
  else s->quiet++;
  /* Keep all leading audio; weak/uncertain speech falls back to the 3s cap. */
  return s->frames>=40 && s->voiced>=8 && s->quiet>=20;
}
#endif
