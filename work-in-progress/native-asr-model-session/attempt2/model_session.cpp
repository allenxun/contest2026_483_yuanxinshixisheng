/* Real decoder Session gate; no simulated speech or Wi-Fi success. */
#define SR_CAPACITY 2048
#include "shared_runtime.hpp"
#include "k7_model_arena.h"
#include "model_lock.h"
#include <cstdio>
#include <cstring>
#include <pthread.h>
#include <nuttx/config.h>
#if defined(CONFIG_MM_FILL_ALLOCATIONS) || defined(CONFIG_MM_KASAN)
#error "RAM model staging requires a separately audited heap initialization"
#endif
extern "C" {
#include "sha256_namespace.h"
}

static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static void lock(void *) { if (pthread_mutex_lock(&mutex)) std::abort(); }
static void unlock(void *) { if (pthread_mutex_unlock(&mutex)) std::abort(); }
static bool verified(const void *p)
{
  sha256_t context;
  unsigned char digest[32];
  sha256_init(&context);
  for (size_t n = 0; n < MODEL_BYTES; )
    {
      size_t amount = MODEL_BYTES - n;
      if (amount > 4096) amount = 4096;
      sha256_update(&context, static_cast<const unsigned char *>(p) + n, amount);
      n += amount;
    }
  sha256_final(&context, digest);
  return !std::memcmp(digest, expected_sha, sizeof(digest));
}

extern "C" int k7_asr_model_session_probe()
{
  // Explicit diagnostic precondition: immutable decoder bytes staged via OTG.
  // This region is mapped as part of the CPU-only model arena.
  const auto *source = reinterpret_cast<const unsigned char *>(0x80000000);
  std::puts("ASR_MODEL BEGIN source-sha256"); std::fflush(stdout);
  if (!verified(source)) { std::puts("ASR_MODEL FAIL source-hash"); return 1; }
  if (k7_model_arena_initialize()) return 1;
  const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
  if (!api) return 1;
  OrtEnv *env = nullptr;
  OrtStatus *status = api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "k7-asr", &env);
  if (status) { api->ReleaseStatus(status); return 1; }
  sr::Port port{nullptr, lock, unlock, k7_model_alloc, k7_model_free,
                K7_MODEL_ARENA_BASE, K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE};
  sr::Runtime runtime(*api, port, 768u * 1024u * 1024u);
  status = runtime.init(env);
  if (status) { api->ReleaseStatus(status); api->ReleaseEnv(env); return 1; }
  int result = 1;
  {
    sr::Lease lease(runtime);
    void *destination = lease.reserve(MODEL_BYTES);
    if (!destination) return 1;
    uintptr_t begin = reinterpret_cast<uintptr_t>(destination);
    if (begin >= 0x80000000 || MODEL_BYTES > 0x80000000 - begin)
      { std::puts("ASR_MODEL FAIL staging-overlap"); return 1; }
    std::memcpy(destination, source, MODEL_BYTES);
    if (!verified(destination)) return 1;
    OrtSessionOptions *options = nullptr;
    status = api->CreateSessionOptions(&options);
    if (!status) status = api->SetSessionExecutionMode(options, ORT_SEQUENTIAL);
    if (!status)
      {
        std::puts("ASR_MODEL BEGIN session"); std::fflush(stdout);
        status = lease.load_verified(options);
      }
    if (status)
      {
        std::printf("ASR_MODEL FAIL code=%d message=%s\n",
                    int(api->GetErrorCode(status)), api->GetErrorMessage(status));
        api->ReleaseStatus(status);
      }
    else
      {
        std::puts("ASR_MODEL PASS decoder-session; inference-not-tested");
        result = 0;
      }
    if (options) api->ReleaseSessionOptions(options);
  }
  std::printf("ASR_MODEL memory peak=%zu live=%zu failures=%zu peak_count=%zu capacity=%u\n",
              runtime.peak, runtime.live, runtime.failures, runtime.peak_count,
              unsigned(SR_CAPACITY));
  std::printf("ASR_MODEL failure reason=%u bytes=%zu (1=state 2=quota 3=records 4=heap)\n",
              runtime.last_failure, runtime.failed_bytes);
  return result;
}
