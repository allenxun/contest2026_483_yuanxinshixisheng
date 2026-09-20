#include "voicelink/tts_runtime.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

int main(int argc, char **argv) {
  if (argc != 5) {
    std::fprintf(stderr, "usage: test-dynamic MODEL TOKENS LEXICON TEXT\n");
    return 64;
  }
  std::vector<int16_t> pcm(8000u * 30u);
  k7_tts_request request{argv[1], argv[2], argv[3], argv[4], nullptr, nullptr};
  size_t frames = 0;
  unsigned rate = 0;
  const int rc = k7_tts_synthesize(&request, pcm.data(), pcm.size(), &frames, &rate);
  uint64_t energy = 0;
  for (size_t i = 0; i < frames; ++i)
    energy += uint64_t(std::abs(int(pcm[i])));
  std::printf("rc=%d frames=%zu sample_rate=%u abs_sum=%llu\n", rc, frames, rate,
              static_cast<unsigned long long>(energy));
  return rc == 0 && frames != 0 && rate == 8000 && energy != 0 ? 0 : 1;
}
