/* POSIX transport regressions; no board/audio/cloud claims. */
#include "../../app/k7agent/cloud/src/board_speech_bridge.c"
#include <assert.h>
static int played;
int k7sound_speak_mono16(const int16_t *pcm,unsigned frames,unsigned capture)
{(void)pcm;(void)frames;(void)capture;played++;return 0;}
int k7sound_capture_stream(unsigned frames,pio_sample_sink sink,void *arg)
{(void)frames;(void)sink;(void)arg;return -EIO;}

int main(void)
{
  int s[2];unsigned char kind;uint32_t length;char bytes[4];
  assert(socketpair(AF_UNIX,SOCK_STREAM,0,s)==0);
  assert(send_packet(s[0],'A',(void *)"test",4)==0);
  assert(header(s[1],&kind,&length)==0 && kind=='A' && length==4);
  assert(transfer(s[1],bytes,4,0)==0 && !memcmp(bytes,"test",4));
  close(s[0]);assert(header(s[1],&kind,&length)<0);close(s[1]);
  /* TTS header rejects oversized and odd PCM before allocation/playback. */
  for(unsigned i=0;i<3;i++)
    {
      assert(socketpair(AF_UNIX,SOCK_STREAM,0,s)==0);
      uint32_t n=i==0?960002:i==1?3:2;
      unsigned char h[5]={i==2?'X':'D',n>>24,n>>16,n>>8,n};
      assert(transfer(s[1],h,5,1)==0);
      assert(tts(s[0])<0 && played==0);
      close(s[0]);close(s[1]);
    }
  assert(socketpair(AF_UNIX,SOCK_STREAM,0,s)==0);
  int16_t pcm[2]={-200,200};
  assert(send_packet(s[1],'D',pcm,sizeof(pcm))==0);
  assert(tts(s[0])==0 && played==1);
  close(s[0]);close(s[1]);
  puts("PASS board speech wire: framing, EOF, invalid PCM, playback dispatch");
  return 0;
}
