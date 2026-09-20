#pragma once
#include "voicelink/tts_runtime.h"
#include "voicelink/speech_pcm.hpp"
#include "k7sound_api.h"
#include <cerrno>
#include <string>
#include <vector>

// Asset paths are supplied only by the validated board resource loader.
// No model path or text is printed. Playback completes before returning.
class NativeSpeechOutput {
 public:
  NativeSpeechOutput(const char* model, const char* tokens, const char* lexicon)
      : model_(model), tokens_(tokens), lexicon_(lexicon) {}

  int say(const std::string& text, unsigned capture_frames = 0) noexcept {
    try {
      std::vector<std::int16_t> pcm(8000 * 30);
      std::size_t frames = 0;
      unsigned rate = 0;
      k7_tts_request request{model_, tokens_, lexicon_, text.c_str(), nullptr, nullptr};
      const int result = k7_tts_synthesize(&request, pcm.data(), pcm.size(), &frames, &rate);
      if (result) return result;
      auto stereo = voicelink::speechPcm(pcm.data(), frames, rate);
      return k7sound_speak_pcm(stereo.data(), unsigned(stereo.size() / 2), capture_frames);
    } catch (const std::bad_alloc&) { return -ENOMEM; }
      catch (...) { return -EINVAL; }
  }
 private:
  const char *model_, *tokens_, *lexicon_;
};
