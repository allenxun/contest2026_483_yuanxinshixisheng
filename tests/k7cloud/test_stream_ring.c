#include "stream_ring.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>

static struct k7_stream_ring ring;

static int frame(uint32_t value)
{
  unsigned i;
  int rc;
  for (i=0;i<K7_STREAM_SAMPLES;i++)
    {
      rc=k7_stream_ring_sample(&ring,value,0);
      if(rc)return rc;
    }
  return 0;
}

int main(void)
{
  unsigned i,j;
  uint8_t pcm[K7_STREAM_BYTES];
  uint32_t seq;
  k7_stream_ring_init(&ring);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==0);
  for(i=0;i<1000;i++)
    {
      assert(frame(i<<16)==0);
      assert(k7_stream_ring_take(&ring,pcm,&seq)==1 && seq==i);
      for(j=0;j<K7_STREAM_SAMPLES;j++)
        assert(pcm[2*j]==(uint8_t)i && pcm[2*j+1]==(uint8_t)(i>>8));
      assert(k7_stream_ring_take(&ring,pcm,&seq)==0);
    }
  assert(frame(UINT32_C(0x80000000))==0);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==1 && pcm[0]==0 && pcm[1]==128);
  assert(frame(UINT32_C(0xffff0000))==0);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==1 && pcm[0]==255 && pcm[1]==255);
  k7_stream_ring_init(&ring);
  for(i=0;i<K7_STREAM_SAMPLES-1;i++) assert(k7_stream_ring_sample(&ring,0,0)==0);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==0);
  assert(k7_stream_ring_sample(&ring,0,0)==0);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==1 && seq==0);
  k7_stream_ring_init(&ring);
  /* A stalled network must not interrupt a complete three-second recording. */
  for(i=0;i<150;i++)assert(frame(i<<16)==0);
  for(i=0;i<150;i++)
    {
      assert(k7_stream_ring_take(&ring,pcm,&seq)==1 && seq==i);
      for(j=0;j<K7_STREAM_SAMPLES;j++)
        assert(pcm[2*j]==(uint8_t)i && pcm[2*j+1]==0);
    }
  assert(k7_stream_ring_take(&ring,pcm,&seq)==0);
  k7_stream_ring_init(&ring);
  for(i=0;i<K7_STREAM_SLOTS;i++)assert(frame(i<<16)==0);
  assert(frame(0)==-ENOSPC);
  assert(k7_stream_ring_take(&ring,pcm,&seq)==-ECANCELED);
  assert(k7_stream_ring_sample(&ring,0,0)==-ECANCELED);
  k7_stream_ring_init(&ring);
  k7_stream_ring_cancel(&ring);
  assert(k7_stream_ring_sample(&ring,0,0)==-ECANCELED);
  assert(k7_stream_ring_take(NULL,pcm,&seq)==-EINVAL);
  puts("PASS ring wrap/order, PCM sign/zero, partial publication, overflow, cancellation");
  return 0;
}
