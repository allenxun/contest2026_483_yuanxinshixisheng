#pragma once

#include "shared_runtime.hpp"
#include "k7_model_arena.h"
#include "k7tts_assets_generated.h"

#include <cstdio>
#include <pthread.h>
#include <stdexcept>
#include <string>

namespace k7_tts {

class ModelStorage {
  pthread_mutex_t mutex_ = PTHREAD_MUTEX_INITIALIZER;
  sr::Runtime runtime_;

  static void lock(void *p) {
    if (pthread_mutex_lock(&static_cast<ModelStorage *>(p)->mutex_))
      std::abort();
  }

  static void unlock(void *p) {
    if (pthread_mutex_unlock(&static_cast<ModelStorage *>(p)->mutex_))
      std::abort();
  }

  static void check(OrtStatus *status) {
    if (!status) return;
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    std::string message = api->GetErrorMessage(status);
    api->ReleaseStatus(status);
    throw std::runtime_error(message);
  }

 public:
  ModelStorage()
      : runtime_(*OrtGetApiBase()->GetApi(ORT_API_VERSION),
                 sr::Port{this, lock, unlock, k7_model_alloc, k7_model_free,
                          K7_MODEL_ARENA_BASE,
                          K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE},
                 K7_MODEL_ARENA_SIZE) {
    static_assert(K7_TTS_MODEL_OFFSET + K7_TTS_MODEL_BYTES <= K7_TTS_ROM_BYTES,
                  "TTS model exceeds verified ROMFS image");
    static_assert(K7_TTS_ROM_ADDRESS >=
                      K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE,
                  "TTS source overlaps model allocator");
  }

  ~ModelStorage() {
    std::printf("TTS_STORAGE peak=%zu live=%zu records=%zu failures=%zu "
                "failed_bytes=%zu reason=%u\n",
                runtime_.peak, runtime_.live, runtime_.peak_count,
                runtime_.failures, runtime_.failed_bytes,
                runtime_.last_failure);
  }

  void initialize(OrtEnv *env, OrtSessionOptions *options) {
    if (k7_model_arena_initialize())
      throw std::runtime_error("TTS model arena");
    check(runtime_.init_borrowed(env));
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    check(api->SetSessionExecutionMode(options, ORT_SEQUENTIAL));
    check(api->SetIntraOpNumThreads(options, 1));
    check(api->SetInterOpNumThreads(options, 1));
    check(api->SetSessionGraphOptimizationLevel(options, ORT_DISABLE_ALL));
    const char *keys[] = {
        "session.use_env_allocators", "session.load_model_format",
        "session.use_ort_model_bytes_directly",
        "session.use_ort_model_bytes_for_initializers"};
    for (unsigned i = 0; i < 4; ++i)
      check(api->AddSessionConfigEntry(options, keys[i],
                                       i == 1 ? "ORT" : "1"));
  }

  void *model_data() const {
    return reinterpret_cast<void *>(uintptr_t(K7_TTS_ROM_ADDRESS +
                                               K7_TTS_MODEL_OFFSET));
  }

  size_t model_size() const { return K7_TTS_MODEL_BYTES; }
};

}  // namespace k7_tts
