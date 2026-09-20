#include "voicelink/tts_runtime.h"
#include "sherpa-onnx/c-api/c-api.h"
#include <cerrno>
#include <cmath>
#include <cstring>
#include <new>
#include <pthread.h>

namespace {
pthread_mutex_t gate = PTHREAD_MUTEX_INITIALIZER;
struct Handles {
  const SherpaOnnxOfflineTts *tts = nullptr;
  const SherpaOnnxGeneratedAudio *audio = nullptr;
  ~Handles() {
    if (audio) SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
    if (tts) SherpaOnnxDestroyOfflineTts(tts);
  }
};
struct Progress {
  const k7_tts_request &request;
  size_t limit;
  size_t count = 0;
  int error = 0;
};
int32_t progress(const float *, int32_t n, void *opaque) {
  auto &p = *static_cast<Progress *>(opaque);
  if (p.request.cancel_requested && p.request.cancel_requested(p.request.cancel_ctx))
    p.error = -ECANCELED;
  else if (n < 0 || size_t(n) > p.limit - p.count)
    p.error = -ENOSPC;
  if (p.error) return 0;
  p.count += size_t(n);
  return 1;
}
}

extern "C" int k7_tts_synthesize(const k7_tts_request *r, int16_t *pcm,
                                  size_t capacity, size_t *frames,
                                  unsigned *sample_rate) {
  if (frames) *frames = 0;
  if (sample_rate) *sample_rate = 0;
  if (!r || !pcm || !frames || !sample_rate || !capacity || capacity > 48000u * 30u)
    return -EINVAL;
  if (!r->model || !r->tokens || !r->lexicon || !r->text || !r->model[0] ||
      !r->tokens[0] || !r->lexicon[0] || !r->text[0]) return -EINVAL;
  if (strnlen(r->text, 241) > 240) return -E2BIG;
  if (r->cancel_requested && r->cancel_requested(r->cancel_ctx)) return -ECANCELED;
  const int lock = pthread_mutex_trylock(&gate);
  if (lock) return -lock;
  struct Unlock { ~Unlock() { pthread_mutex_unlock(&gate); } } unlock;
  try {
    Handles h;
    SherpaOnnxOfflineTtsConfig config{};
    config.model.vits.model = r->model;
    config.model.vits.tokens = r->tokens;
    config.model.vits.lexicon = r->lexicon;
    config.model.vits.noise_scale = 0.667f;
    config.model.vits.noise_scale_w = 0.8f;
    config.model.vits.length_scale = 1.0f;
    config.model.num_threads = 1;
    config.model.provider = "cpu";
    config.max_num_sentences = 1;
    h.tts = SherpaOnnxCreateOfflineTts(&config);
    if (!h.tts) return -EIO;
    if (r->cancel_requested && r->cancel_requested(r->cancel_ctx)) return -ECANCELED;
    Progress p{*r, capacity};
    h.audio = SherpaOnnxOfflineTtsGenerateWithCallbackWithArg(h.tts, r->text, 0,
                                                            1.0f, progress, &p);
    if (p.error) return p.error;
    if (r->cancel_requested && r->cancel_requested(r->cancel_ctx)) return -ECANCELED;
    if (!h.audio || !h.audio->samples || h.audio->n <= 0) return -ENODATA;
    if (size_t(h.audio->n) > capacity) return -ENOSPC;
    if (h.audio->sample_rate < 8000 || h.audio->sample_rate > 48000) return -ERANGE;
    // Validate before exposing any PCM, avoiding partial audio on malformed output.
    for (int i = 0; i < h.audio->n; ++i)
      if (!std::isfinite(h.audio->samples[i])) return -EIO;
    for (int i = 0; i < h.audio->n; ++i) {
      const float x = h.audio->samples[i];
      pcm[i] = x >= 1.0f ? 32767 : x <= -1.0f ? -32768 : int16_t(x * 32767.0f);
    }
    *frames = size_t(h.audio->n);
    *sample_rate = unsigned(h.audio->sample_rate);
    return 0;
  } catch (const std::bad_alloc &) { return -ENOMEM; }
    catch (...) { return -EIO; }
}
