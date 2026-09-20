#include "voicelink/tts_runtime.h"
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

int main(int argc, char **argv) {
  if (argc != 4) {
    std::fprintf(stderr, "usage: test-real MODEL TOKENS LEXICON\n");
    return 64;
  }
  std::vector<int16_t> pcm(8000u * 12u);
  k7_tts_request request{argv[1], argv[2], argv[3], "你好，网络配置已开始。",
                         nullptr, nullptr};
  size_t frames = 0;
  unsigned rate = 0;
  const int rc = k7_tts_synthesize(&request, pcm.data(), pcm.size(), &frames, &rate);
  if (rc != 0 || frames == 0 || rate != 8000) {
    std::fprintf(stderr, "synthesis failed rc=%d frames=%zu rate=%u\n", rc,
                 frames, rate);
    return 1;
  }
  uint64_t energy = 0;
  for (size_t i = 0; i < frames; ++i)
    energy += uint64_t(std::abs(int(pcm[i])));
  if (energy == 0) {
    std::fputs("synthesis returned silent PCM\n", stderr);
    return 2;
  }
  std::printf("PASS frames=%zu sample_rate=%u abs_sum=%llu\n", frames, rate,
              static_cast<unsigned long long>(energy));
  return 0;
}
