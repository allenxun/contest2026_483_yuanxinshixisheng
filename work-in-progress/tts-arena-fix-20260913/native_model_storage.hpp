#pragma once

#include "shared_model_runtime.hpp"
#include <nuttx/mm/k7_model_arena.h>

#include <nuttx/config.h>
#include <pthread.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>

#if defined(CONFIG_MM_FILL_ALLOCATIONS) || defined(CONFIG_MM_KASAN)
#error "Re-audit staged model memory before enabling heap fill or KASAN"
#endif

extern "C" {
#include "sha256_namespace.h"
}

namespace k7_asr {

class ModelStorage final {
  static bool hash(const void *data, size_t bytes,
                   const unsigned char *expected) {
    sha256_t context;
    unsigned char digest[32];
    sha256_init(&context);
    const auto *source = static_cast<const unsigned char *>(data);
    for (size_t offset = 0; offset < bytes;) {
      size_t count = bytes - offset;
      if (count > 4096) count = 4096;
      sha256_update(&context, source + offset, count);
      offset += count;
    }
    sha256_final(&context, digest);
    return std::memcmp(digest, expected, sizeof(digest)) == 0;
  }

  static void check(OrtStatus *status) {
    if (!status) return;
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    std::string message = api->GetErrorMessage(status);
    api->ReleaseStatus(status);
    throw std::runtime_error(message);
  }

 public:
  sr_shared::Runtime &runtime;
  sr_shared::Lease encoder;
  sr_shared::Lease decoder;
  void *encoder_bytes = nullptr;
  void *decoder_bytes = nullptr;

  static constexpr size_t encoder_size = 166189616;
  static constexpr size_t decoder_size = 72024848;

  ModelStorage()
      : runtime(sr_shared::shared_model_runtime()),
        encoder(runtime),
        decoder(runtime) {
    static_assert(K7_MODEL_ARENA_BASE == UINT64_C(0x60000000),
                  "re-audit ASR arena base");
    static_assert(K7_MODEL_ARENA_SIZE == UINT64_C(0x20000000),
                  "staged ASR/TTS runtime must use a 512 MiB arena");
    static_assert(K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE <=
                      UINT64_C(0x80000000),
                  "ASR allocator overlaps encoder source");
  }

  ~ModelStorage() {
    decoder.close();
    encoder.close();
    std::printf(
        "ASR_STORAGE peak=%zu live=%zu records=%zu failures=%zu "
        "failed_bytes=%zu reason=%u available=%zu\n",
        runtime.peak, runtime.live, runtime.peak_count, runtime.failures,
        runtime.failed_bytes, runtime.last_failure, k7_model_available());
  }

  void initialize(OrtEnv *environment, OrtSessionOptions *options) {
    static const unsigned char expected_encoder[32] = {
        248, 31, 158, 101, 110, 33, 188, 108, 131, 80, 183, 160, 78, 53,
        99, 190, 227, 85, 45, 208, 224, 71, 164, 75, 94, 156, 151, 143,
        209, 136, 193, 175};
    static const unsigned char expected_decoder[32] = {
        15, 88, 202, 75, 215, 119, 40, 216, 229, 18, 184, 82, 239, 245,
        142, 154, 238, 221, 144, 207, 162, 1, 106, 228, 3, 121, 180,
        112, 10, 120, 218, 20};
    const void *source_encoder = reinterpret_cast<const void *>(0x80000000);
    const void *source_decoder = reinterpret_cast<const void *>(0x90000000);
    if (!hash(source_encoder, encoder_size, expected_encoder) ||
        !hash(source_decoder, decoder_size, expected_decoder)) {
      throw std::runtime_error("ASR staged model hash");
    }
    if (k7_model_arena_initialize()) {
      throw std::runtime_error("ASR model arena");
    }
    check(runtime.init_borrowed(environment));
    encoder_bytes = encoder.reserve(encoder_size);
    decoder_bytes = decoder.reserve(decoder_size);
    if (!encoder_bytes || !decoder_bytes) {
      throw std::runtime_error("ASR model reservation");
    }
    for (const auto &item : {
             std::pair<void *, size_t>{encoder_bytes, encoder_size},
             std::pair<void *, size_t>{decoder_bytes, decoder_size}}) {
      const uintptr_t address = reinterpret_cast<uintptr_t>(item.first);
      if (address < K7_MODEL_ARENA_BASE || address >= UINT64_C(0x80000000) ||
          item.second > UINT64_C(0x80000000) - address) {
        throw std::runtime_error("ASR staging overlap");
      }
    }
    std::memcpy(encoder_bytes, source_encoder, encoder_size);
    std::memcpy(decoder_bytes, source_decoder, decoder_size);
    if (!hash(encoder_bytes, encoder_size, expected_encoder) ||
        !hash(decoder_bytes, decoder_size, expected_decoder)) {
      throw std::runtime_error("ASR persistent model hash");
    }

    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
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

}  // namespace k7_asr
