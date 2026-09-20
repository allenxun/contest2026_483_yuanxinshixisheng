#include <assert.h>
#include <stdio.h>
#include "../../app/k7agent/cloud/src/command_endpoint.h"
static int frame(struct k7_command_endpoint *s,int value)
{
  for(unsigned i=0;i<320;i++)k7_endpoint_sample(s,(int16_t)(i%2?value:-value));
  return k7_endpoint_frame(s);
}
int main(void)
{
  struct k7_command_endpoint s={0};
  for(unsigned i=0;i<150;i++)assert(!frame(&s,90)); /* Silence never cuts onset wait. */
  s=(struct k7_command_endpoint){0};
  for(unsigned i=0;i<30;i++)assert(!frame(&s,900));
  for(unsigned i=0;i<19;i++)assert(!frame(&s,90));
  assert(frame(&s,90) && s.frames==50 && s.last_active==30); /* 600ms speech +400ms tail. */
  s=(struct k7_command_endpoint){0};
  for(unsigned i=0;i<15;i++)assert(!frame(&s,800));
  for(unsigned i=0;i<15;i++)assert(!frame(&s,90)); /* Internal 300ms pause survives. */
  for(unsigned i=0;i<15;i++)assert(!frame(&s,800));
  for(unsigned i=0;i<19;i++)assert(!frame(&s,90));
  assert(frame(&s,90));
  s=(struct k7_command_endpoint){0};
  for(unsigned i=0;i<150;i++)assert(!frame(&s,250)); /* Faint audio keeps old 3s fallback. */
  s=(struct k7_command_endpoint){0};
  for(unsigned i=0;i<320;i++)k7_endpoint_sample(&s,INT16_MIN);
  assert(!k7_endpoint_frame(&s) && s.voiced==1); /* No abs/sign overflow. */
  puts("PASS: early endpoint, pause retention, quiet/faint fallback, signed sample bounds");
}
