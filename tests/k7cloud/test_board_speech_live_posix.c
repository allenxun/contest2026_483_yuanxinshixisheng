/* Synthetic zero audio through the exact board C sender. No microphone. */
#include "../../app/k7agent/cloud/src/board_speech_bridge.c"
int k7sound_speak_mono16(const int16_t *p,unsigned n,unsigned c)
{(void)p;(void)n;(void)c;return 0;}
int k7sound_capture_stream(unsigned n,pio_sample_sink sink,void *arg)
{
  for(unsigned i=0;i<n;i++)
    {
      int rc=sink(arg,0,0);if(rc)return rc;
      if(i%320==319)usleep(20000);
    }
  return 0;
}
int main(void){return k7cloud_board_speech("asr-live","10.3.1.125")?1:0;}
