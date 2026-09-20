#include "speech_runtime_gate.h"

#include <pthread.h>

#include <cstdlib>

namespace {
pthread_mutex_t g_speech_runtime_gate = PTHREAD_MUTEX_INITIALIZER;
}

extern "C" int k7_speech_runtime_try_acquire(void) {
  const int error = pthread_mutex_trylock(&g_speech_runtime_gate);
  return error == 0 ? 0 : -error;
}

extern "C" void k7_speech_runtime_release(void) {
  if (pthread_mutex_unlock(&g_speech_runtime_gate)) {
    std::abort();
  }
}
