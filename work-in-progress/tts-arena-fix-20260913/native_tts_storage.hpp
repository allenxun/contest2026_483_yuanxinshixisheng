#pragma once

#include "shared_model_runtime.hpp"
#include "k7tts_assets_generated.h"

#include <nuttx/mm/k7_model_arena.h>
#include <pthread.h>

#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>

extern "C" {
#include "sha256_namespace.h"
}

namespace k7_tts {

class ModelStorage final {
  static bool hash(const void *data, size_t bytes,
                   const unsigned char *expected) {
    sha256_t context;
    unsigned char digest[32];
    sha256_init(&context);
    const auto *source = static_cast<const unsigned char *>(data);
    for (size_t offset = 0; offset < bytes;) {
      size_t count = bytes - offset;
      if (count > 4096) {
        count = 4096;
      }
      sha256_update(&context, source + offset, count);
      offset += count;
    }
    sha256_final(&context, digest);
    return std::memcmp(digest, expected, sizeof(digest)) == 0;
  }

  static void check(OrtStatus *status) {
    if (!status) {
      return;
    }
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    std::string message = api->GetErrorMessage(status);
    api->ReleaseStatus(status);
    throw std::runtime_error(message);
  }

 public:
  sr_shared::Runtime &runtime;

  ModelStorage()
      : runtime(sr_shared::shared_model_runtime()) {
    static_assert(K7_MODEL_ARENA_BASE == UINT64_C(0x60000000),
                  "re-audit model arena base");
    static_assert(K7_MODEL_ARENA_SIZE == UINT64_C(0x20000000),
                  "TTS/ASR source preservation requires a 512 MiB arena");
    static_assert(K7_TTS_MODEL_OFFSET + K7_TTS_MODEL_BYTES <= K7_TTS_ROM_BYTES,
                  "TTS model exceeds verified ROMFS image");
    static_assert(K7_TTS_ROM_ADDRESS >=
                      K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE,
                  "TTS source overlaps allocator");
  }

  ModelStorage(const ModelStorage &) = delete;
  ModelStorage &operator=(const ModelStorage &) = delete;

  ~ModelStorage() {
    std::printf(
        "TTS_STORAGE peak=%zu live=%zu records=%zu failures=%zu "
        "failed_bytes=%zu reason=%u available=%zu\n",
        runtime.peak, runtime.live, runtime.peak_count, runtime.failures,
        runtime.failed_bytes, runtime.last_failure, k7_model_available());
  }

  const void *model_data() const {
    return reinterpret_cast<const void *>(
        K7_TTS_ROM_ADDRESS + K7_TTS_MODEL_OFFSET);
  }

  size_t model_size() const { return K7_TTS_MODEL_BYTES; }

  void initialize(OrtEnv *environment, OrtSessionOptions *options) {
    static const unsigned char expected[32] = {
        0x97, 0x08, 0x4a, 0xf5, 0x7d, 0xe4, 0x13, 0x5f,
        0xc9, 0x21, 0x78, 0x51, 0x38, 0x6b, 0x1f, 0x6d,
        0x51, 0x1a, 0xe2, 0x2e, 0xba, 0x01, 0xd9, 0xc5,
        0xd9, 0xed, 0xf0, 0x4f, 0x0e, 0x2a, 0xdc, 0x63,
    };
    if (k7_model_arena_initialize()) {
      throw std::runtime_error("TTS model arena");
    }
    if (!hash(model_data(), model_size(), expected)) {
      throw std::runtime_error("TTS staged model hash");
    }
    check(runtime.init_borrowed(environment));

    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    // A registered OrtDeviceAllocator is selected only when the CPU EP does
    // not create its own arena allocator. Leaving the CPU arena enabled made
    // Session initialization fall back to the small NuttX system heap.
    check(api->DisableCpuMemArena(options));
    check(api->SetSessionExecutionMode(options, ORT_SEQUENTIAL));
    check(api->SetIntraOpNumThreads(options, 1));
    check(api->SetInterOpNumThreads(options, 1));
    check(api->SetSessionGraphOptimizationLevel(options, ORT_DISABLE_ALL));
    const char *keys[] = {
        "session.use_env_allocators",
        "session.load_model_format",
        "session.use_ort_model_bytes_directly",
        "session.use_ort_model_bytes_for_initializers",
    };
    const char *values[] = {"1", "ORT", "1", "1"};
    for (unsigned index = 0; index < 4; ++index) {
      check(api->AddSessionConfigEntry(options, keys[index], values[index]));
    }
  }
};

}  // namespace k7_tts
