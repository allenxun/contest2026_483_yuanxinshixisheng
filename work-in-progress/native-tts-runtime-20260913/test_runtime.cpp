#include "voicelink/tts_runtime.h"
#include "sherpa-onnx/c-api/c-api.h"
#include <cassert>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <string>
static int mode, destroyed, freed;
static float samples[4] = {-2.0f, 0.0f, .5f, 2.0f};
static SherpaOnnxGeneratedAudio audio{samples, 4, 22050};
extern "C" const SherpaOnnxOfflineTts *SherpaOnnxCreateOfflineTts(const SherpaOnnxOfflineTtsConfig *c) {
  assert(c->model.num_threads == 1);
  return mode == 1 ? nullptr : reinterpret_cast<const SherpaOnnxOfflineTts *>(1);
}
extern "C" void SherpaOnnxDestroyOfflineTts(const SherpaOnnxOfflineTts *) { ++destroyed; }
extern "C" void SherpaOnnxDestroyOfflineTtsGeneratedAudio(const SherpaOnnxGeneratedAudio *) { ++freed; }
extern "C" const SherpaOnnxGeneratedAudio *SherpaOnnxOfflineTtsGenerateWithCallbackWithArg(
    const SherpaOnnxOfflineTts *, const char *, int32_t, float,
    SherpaOnnxGeneratedAudioCallbackWithArg cb, void *arg) {
  if (mode == 2) return nullptr;
  cb(samples, 4, arg);
  return &audio;
}
static int cancel(void *) { return 1; }
int main() {
  k7_tts_request r{"model", "tokens", "lexicon", "你好", nullptr, nullptr};
  int16_t pcm[4]{};
  size_t n = 77;
  unsigned rate = 99;
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == 0);
  assert(n == 4 && rate == 22050 && pcm[0] == -32768 && pcm[3] == 32767);
  assert(destroyed == 1 && freed == 1);
  assert(k7_tts_synthesize(&r, pcm, 3, &n, &rate) == -ENOSPC && !n && !rate);
  assert(destroyed == 2 && freed == 2);
  mode = 1;
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == -EIO);
  mode = 2;
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == -ENODATA);
  mode = 0;
  samples[0] = NAN;
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == -EIO && !n);
  samples[0] = 0;
  r.cancel_requested = cancel;
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == -ECANCELED);
  r.cancel_requested = nullptr;
  std::string long_text(241, 'a'); r.text = long_text.c_str();
  assert(k7_tts_synthesize(&r, pcm, 4, &n, &rate) == -E2BIG);
  assert(k7_tts_synthesize(nullptr, pcm, 4, &n, &rate) == -EINVAL);
  assert(destroyed == 4 && freed == 3);
  puts("PASS: synthesis contract, saturation, capacity, missing engine/audio, NaN, cancellation, text bound, cleanup");
}
