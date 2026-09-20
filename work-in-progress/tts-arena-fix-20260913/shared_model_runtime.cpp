#include "shared_model_runtime.hpp"

#include <nuttx/mm/k7_model_arena.h>
#include <pthread.h>

#include <cstdlib>

namespace sr_shared {
namespace {

struct SharedState final {
  pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
  Runtime runtime;

  static void lock(void *opaque) {
    auto *state = static_cast<SharedState *>(opaque);
    if (pthread_mutex_lock(&state->mutex)) std::abort();
  }

  static void unlock(void *opaque) {
    auto *state = static_cast<SharedState *>(opaque);
    if (pthread_mutex_unlock(&state->mutex)) std::abort();
  }

  SharedState()
      : runtime(*OrtGetApiBase()->GetApi(ORT_API_VERSION),
                Port{this, lock, unlock, k7_model_alloc, k7_model_free,
                     K7_MODEL_ARENA_BASE,
                     K7_MODEL_ARENA_BASE + K7_MODEL_ARENA_SIZE},
                K7_MODEL_ARENA_SIZE) {
    static_assert(K7_MODEL_ARENA_BASE == UINT64_C(0x60000000),
                  "re-audit shared speech arena base");
    static_assert(K7_MODEL_ARENA_SIZE == UINT64_C(0x20000000),
                  "shared speech runtime requires a 512 MiB arena");
  }
};

SharedState state;

}  // namespace

Runtime &shared_model_runtime() { return state.runtime; }

}  // namespace sr_shared
