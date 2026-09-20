#include "voicelink/speech_pcm.hpp"
#include <cassert>
int main() {
  const std::int16_t input[] = {-32768, 32767, 0};
  auto out = voicelink::speechPcm(input, 3, 8000);
  assert(out.size() == 12);
  assert(out[0] == 0x80000000u && out[2] == 0);
  assert(out[4] == 0x7fff0000u && out[6] == 0x3fff0000u);
  assert(out[8] == 0 && out[10] == 0);
  for (unsigned i=0;i<out.size();i+=2) assert(out[i]==out[i+1]);
  auto direct = voicelink::speechPcm(input, 3, 16000);
  assert(direct.size()==6 && direct[2]==0x7fff0000u);
  for (unsigned rate : {0u, 7999u, 24000u}) {
    bool caught=false;
    try { voicelink::speechPcm(input,3,rate); } catch (const std::invalid_argument&) { caught=true; }
    assert(caught);
  }
}
