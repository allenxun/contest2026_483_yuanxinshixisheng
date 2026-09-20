#pragma once

#define SR_CAPACITY 2048
#include "shared_runtime.hpp"
#include <nuttx/mm/k7_model_arena.h>
#include <pthread.h>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <sys/stat.h>

namespace k7_tts {

class ModelStorage final {
  pthread_mutex_t mutex_ = PTHREAD_MUTEX_INITIALIZER;

  static void lock(void *p) {
    if (pthread_mutex_lock(&static_cast<ModelStorage *>(p)->mutex_)) std::abort();
  }
  static void unlock(void *p) {
    if (pthread_mutex_unlock(&static_cast<ModelStorage *>(p)->mutex_)) std::abort();
  }
  static void check(OrtStatus *s) {
    if (!s) return;
    const auto *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    std::string message = api->GetErrorMessage(s);
    api->ReleaseStatus(s);
    throw std::runtime_error(message);
  }

 public:
  static constexpr size_t expected_model_size = 31190816;

  sr::Runtime runtime;
  sr::Lease model;
  void *model_bytes = nullptr;

  ModelStorage()
      : runtime(*OrtGetApiBase()->GetApi(ORT_API_VERSION),
                sr::Port{this, lock, unlock, k7_model_alloc, k7_model_free,
                         K7_MODEL_ARENA_BASE,
                         K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE},
                K7_MODEL_ARENA_SIZE),
        model(runtime) {}

  ~ModelStorage() {
    model.close();
    model_bytes = nullptr;
    std::printf("TTS_STORAGE peak=%zu live=%zu records=%zu failures=%zu "
                "failed_bytes=%zu reason=%u\n",
                runtime.peak, runtime.live, runtime.peak_count, runtime.failures,
                runtime.failed_bytes, runtime.last_failure);
  }

  void initialize(OrtEnv *env, OrtSessionOptions *options,
                  const char *model_path) {
    struct stat st {};
    if (!model_path || stat(model_path, &st) || st.st_size < 0 ||
        static_cast<size_t>(st.st_size) != expected_model_size)
      throw std::runtime_error("TTS staged model size");
    if (k7_model_arena_initialize())
      throw std::runtime_error("TTS model arena");
    check(runtime.init_borrowed(env));
    model_bytes = model.reserve(expected_model_size);
    if (!model_bytes) throw std::runtime_error("TTS model reservation");

    std::FILE *f = std::fopen(model_path, "rb");
    if (!f) throw std::runtime_error("TTS staged model open");
    size_t offset = 0;
    while (offset != expected_model_size) {
      size_t n = std::fread(static_cast<unsigned char *>(model_bytes) + offset,
                            1, expected_model_size - offset, f);
      if (!n) {
        std::fclose(f);
        throw std::runtime_error("TTS staged model read");
      }
      offset += n;
    }
    const int trailing = std::fgetc(f);
    const int read_error = std::ferror(f);
    const int close_error = std::fclose(f);
    if (trailing != EOF || read_error || close_error)
      throw std::runtime_error("TTS staged model trailing data");

    const auto *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    check(api->SetSessionExecutionMode(options, ORT_SEQUENTIAL));
    check(api->SetIntraOpNumThreads(options, 1));
    check(api->SetInterOpNumThreads(options, 1));
    check(api->SetSessionGraphOptimizationLevel(options, ORT_DISABLE_ALL));
    const char *keys[] = {
        "session.use_env_allocators", "session.load_model_format",
        "session.use_ort_model_bytes_directly",
        "session.use_ort_model_bytes_for_initializers"};
    for (unsigned i = 0; i < 4; ++i)
      check(api->AddSessionConfigEntry(options, keys[i], i == 1 ? "ORT" : "1"));
  }
};

}  // namespace k7_tts
