#include "voicelink/tts_runtime.h"
#include "speech_runtime_gate.h"
#include "sherpa-onnx/c-api/c-api.h"
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <new>
#include <pthread.h>

namespace {
constexpr int32_t kMaleSpeakerId = 21;

struct AudioHandle {
  const SherpaOnnxGeneratedAudio *audio = nullptr;
  ~AudioHandle() {
    if (audio) SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
  }
};

// Model/session initialization dominates latency on K7. The shared speech gate
// guarantees serialized access, so retain the immutable TTS session and only
// recreate the generated-audio object for each prompt.
const SherpaOnnxOfflineTts *g_tts = nullptr;
char g_model[256]{};
char g_tokens[256]{};
char g_lexicon[256]{};

int monotonic_ms(uint64_t &out) noexcept {
  timespec value{};
  if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0) return -EIO;
  out = uint64_t(value.tv_sec) * 1000 + uint64_t(value.tv_nsec) / 1000000;
  return 0;
}

bool remember_path(char *destination, size_t capacity, const char *source) {
  const size_t bytes = std::strlen(source) + 1;
  if (bytes > capacity) return false;
  std::memcpy(destination, source, bytes);
  return true;
}
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
  const int lock = k7_speech_runtime_try_acquire();
  if (lock < 0) return lock;
  struct Unlock { ~Unlock() { k7_speech_runtime_release(); } } unlock;
  try {
    uint64_t start = 0;
    if (monotonic_ms(start)) return -EIO;
    const bool cache_hit = g_tts != nullptr;
    if (!g_tts) {
      if (!remember_path(g_model, sizeof(g_model), r->model) ||
          !remember_path(g_tokens, sizeof(g_tokens), r->tokens) ||
          !remember_path(g_lexicon, sizeof(g_lexicon), r->lexicon)) return -ENAMETOOLONG;
      SherpaOnnxOfflineTtsConfig config{};
      // Sherpa validates this path before constructing the patched VITS model.
      // Keep the mounted ROMFS path here; the K7 storage backend still creates
      // the ORT session directly from the retained DDR model bytes.
      config.model.vits.model = r->model;
      config.model.vits.tokens = r->tokens;
      config.model.vits.lexicon = r->lexicon;
      config.model.vits.noise_scale = 0.667f;
      config.model.vits.noise_scale_w = 0.8f;
      config.model.vits.length_scale = 1.0f;
      config.model.num_threads = 1;
      config.model.provider = "cpu";
      config.max_num_sentences = 1;
      g_tts = SherpaOnnxCreateOfflineTts(&config);
      if (!g_tts) {
        g_model[0] = g_tokens[0] = g_lexicon[0] = '\0';
        return -EIO;
      }
    } else if (std::strcmp(g_model, r->model) ||
               std::strcmp(g_tokens, r->tokens) ||
               std::strcmp(g_lexicon, r->lexicon)) {
      return -EINVAL;
    }
    if (r->cancel_requested && r->cancel_requested(r->cancel_ctx)) return -ECANCELED;
    const int32_t speakers = SherpaOnnxOfflineTtsNumSpeakers(g_tts);
    if (speakers <= kMaleSpeakerId) return -ERANGE;
    uint64_t initialized = 0;
    if (monotonic_ms(initialized)) return -EIO;
    std::printf("TTS_CACHE hit=%u init_seconds=%.3f speakers=%d sid=%d\n",
                cache_hit ? 1u : 0u, double(initialized - start) / 1000.0,
                int(speakers), int(kMaleSpeakerId));
    std::fflush(stdout);
    AudioHandle h;
    Progress p{*r, capacity};
    h.audio = SherpaOnnxOfflineTtsGenerateWithCallbackWithArg(
        g_tts, r->text, kMaleSpeakerId, 1.0f, progress, &p);
    if (p.error) return p.error;
    if (r->cancel_requested && r->cancel_requested(r->cancel_ctx)) return -ECANCELED;
    if (!h.audio || !h.audio->samples || h.audio->n <= 0) return -ENODATA;
    if (size_t(h.audio->n) > capacity) return -ENOSPC;
    if (h.audio->sample_rate < 8000 || h.audio->sample_rate > 48000) return -ERANGE;
    // Validate before exposing any PCM, avoiding partial audio on malformed output.
    float peak = 0.0f;
    std::size_t clipped = 0;
    for (int i = 0; i < h.audio->n; ++i) {
      if (!std::isfinite(h.audio->samples[i])) return -EIO;
      const float magnitude = std::fabs(h.audio->samples[i]);
      if (magnitude > peak) peak = magnitude;
      if (magnitude >= 1.0f) ++clipped;
    }
    for (int i = 0; i < h.audio->n; ++i) {
      const float x = h.audio->samples[i];
      pcm[i] = x >= 1.0f ? 32767 : x <= -1.0f ? -32768 : int16_t(x * 32767.0f);
    }
    *frames = size_t(h.audio->n);
    *sample_rate = unsigned(h.audio->sample_rate);
    uint64_t finished = 0;
    if (monotonic_ms(finished)) return -EIO;
    std::printf("TTS_AUDIO frames=%zu rate=%u peak_milli=%u clipped=%zu "
                "cache=%s seconds=%.3f speakers=%d sid=%d\n",
                *frames, *sample_rate,
                unsigned((peak >= 65.535f ? 65.535f : peak) * 1000.0f),
                clipped, cache_hit ? "hit" : "miss",
                double(finished - start) / 1000.0, int(speakers),
                int(kMaleSpeakerId));
    return 0;
  } catch (const std::bad_alloc &) { return -ENOMEM; }
    catch (...) { return -EIO; }
}
