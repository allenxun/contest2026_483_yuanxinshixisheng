#pragma once

#include "shared_runtime.hpp"
#include "k7tts_assets_generated.h"

#include <nuttx/mm/k7_model_arena.h>

#include <cstdio>
#include <pthread.h>
#include <stdexcept>
#include <string>

namespace k7_tts_storage {

class ModelStorage final {
  pthread_mutex_t mutex_ = PTHREAD_MUTEX_INITIALIZER;

  static void lock(void *opaque) {
    if (pthread_mutex_lock(&static_cast<ModelStorage *>(opaque)->mutex_)) {
      std::abort();
    }
  }

  static void unlock(void *opaque) {
    if (pthread_mutex_unlock(&static_cast<ModelStorage *>(opaque)->mutex_)) {
      std::abort();
    }
  }

  static void check(OrtStatus *status) {
    if (!status) return;
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    const char *raw = api->GetErrorMessage(status);
    const std::string message = raw ? raw : "ORT TTS setup";
    api->ReleaseStatus(status);
    throw std::runtime_error(message);
  }

 public:
  static constexpr uintptr_t kModelAddress =
      static_cast<uintptr_t>(K7_TTS_ROM_ADDRESS) + 0x730u;
  static constexpr size_t kModelBytes = 31190816u;

  static const char *model_path() { return "/mnt/k7tts/vits.ort"; }

  Runtime runtime;

  ModelStorage()
      : runtime(*OrtGetApiBase()->GetApi(ORT_API_VERSION),
                Port{this, lock, unlock, k7_model_alloc, k7_model_free,
                     static_cast<uintptr_t>(K7_MODEL_ARENA_BASE),
                     static_cast<uintptr_t>(K7_MODEL_ARENA_BASE +
                                            K7_MODEL_ARENA_SIZE)},
                static_cast<size_t>(K7_MODEL_ARENA_SIZE)) {
    static_assert(K7_TTS_ROM_ADDRESS == UINT64_C(0x96000000),
                  "unexpected TTS ROMFS address");
    static_assert(K7_TTS_ROM_BYTES == UINT32_C(33235968),
                  "unexpected TTS ROMFS byte count");
    static_assert(K7_TTS_ROM_CRC32 == UINT32_C(0x9efc1996),
                  "unexpected TTS ROMFS CRC32");
    static_assert(K7_TTS_ROM_ADDRESS >=
                      K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE,
                  "TTS ROMFS overlaps the model allocator");
    static_assert(kModelAddress >= K7_TTS_ROM_ADDRESS,
                  "TTS model address wrapped");
    static_assert(kModelBytes <=
                      K7_TTS_ROM_ADDRESS + K7_TTS_ROM_BYTES - kModelAddress,
                  "TTS model exceeds the verified ROMFS image");
  }

  ~ModelStorage() {
    std::printf(
        "TTS_STORAGE peak=%zu live=%zu records=%zu failures=%zu "
        "failed_bytes=%zu reason=%u\n",
        runtime.peak, runtime.live, runtime.peak_count, runtime.failures,
        runtime.failed_bytes, runtime.last_failure);
  }

  void initialize(OrtEnv *env, OrtSessionOptions *options,
                  const std::string &requested_path) {
    if (requested_path != model_path()) {
      throw std::runtime_error("TTS model path is not the verified ROMFS asset");
    }
    if (k7_model_arena_initialize() < 0) {
      throw std::runtime_error("TTS model arena initialization");
    }
    check(runtime.initialize_borrowed(env));

    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    check(api->SetSessionExecutionMode(options, ORT_SEQUENTIAL));
    check(api->SetIntraOpNumThreads(options, 1));
    check(api->SetInterOpNumThreads(options, 1));
    check(api->SetSessionGraphOptimizationLevel(options, ORT_DISABLE_ALL));
    // A one-shot TTS Session cannot reuse a learned memory pattern.
    check(api->DisableMemPattern(options));

    static constexpr const char *keys[] = {
        "session.use_env_allocators",
        "session.load_model_format",
        "session.use_ort_model_bytes_directly",
        "session.use_ort_model_bytes_for_initializers",
    };
    static constexpr const char *values[] = {"1", "ORT", "1", "1"};
    for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i) {
      check(api->AddSessionConfigEntry(options, keys[i], values[i]));
    }
  }

  const void *model_data() const {
    return reinterpret_cast<const void *>(kModelAddress);
  }
};

}  // namespace k7_tts_storage
