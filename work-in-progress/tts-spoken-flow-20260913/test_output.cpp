#include <native_speech_output.hpp>
#include <cstring>
#include <cassert>
static int fail=0, plays=0;
static unsigned recorded=0;
extern "C" int k7_tts_synthesize(const k7_tts_request* r, int16_t* pcm,
    size_t capacity, size_t* frames, unsigned* rate) {
  assert(r && capacity>=2);
  assert(std::strlen(r->text)<=180);
  if(fail) return -EIO;
  pcm[0]=-32768;pcm[1]=32767;*frames=2;*rate=8000;
  return 0;
}
extern "C" int k7sound_speak_pcm(const uint32_t* pcm,unsigned frames,unsigned capture) {
  assert(frames==4 && pcm[0]==0x80000000u && pcm[4]==0x7fff0000u);
  ++plays;recorded=capture;return 0;
}
int main() {
  NativeSpeechOutput output("model","tokens","lexicon");
  assert(output.say("请说话",48000)==0 && plays==1 && recorded==48000);
  fail=1;
  assert(output.say("请说话",48000)==-EIO && plays==1);
  fail=0;
  std::string long_text;
  for(int i=0;i<90;++i)long_text+="你好";
  assert(output.say(long_text,48000)==0 && plays==4 && recorded==48000);
}
