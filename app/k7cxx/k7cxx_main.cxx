/* Native runtime prerequisite probe; no model, radio or storage writes. */
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <sys/types.h>

namespace {
volatile unsigned constructed;
struct Startup { Startup() { constructed = 0x435858; } } startup;
struct Cleanup {
  unsigned &count;
  ~Cleanup() { ++count; }
};
/* Static storage remains valid if the bounded wait expires. */
struct WorkerState {
  std::mutex mutex;
  std::condition_variable cv;
  bool done = false;
  unsigned value = 0;
} state;
std::atomic<bool> started{false};

int probe()
{
  if (constructed != 0x435858) return 2;
  std::vector<std::string> words{"native", "openvela", "cpu"};
  if (words.at(1) != "openvela") return 3;
  unsigned cleaned = 0;
  try {
    Cleanup guard{cleaned};
    throw std::runtime_error("expected probe exception");
  } catch (const std::runtime_error &) { }
  if (cleaned != 1) return 4;
  void *raw = nullptr;
  if (posix_memalign(&raw, 64, 4096) != 0) return 5;
  std::unique_ptr<void, decltype(&std::free)> memory(raw, &std::free);
  if (reinterpret_cast<std::uintptr_t>(raw) % 64 != 0) return 6;
  auto *bytes = static_cast<unsigned char *>(raw);
  for (unsigned i = 0; i < 4096; ++i) bytes[i] = static_cast<unsigned char>(i);
  for (unsigned i = 0; i < 4096; ++i)
    if (bytes[i] != static_cast<unsigned char>(i)) return 7;
  const auto before = std::chrono::steady_clock::now();
  std::thread worker([] {
    std::lock_guard<std::mutex> lock(state.mutex);
    state.value = 0x3576;
    state.done = true;
    state.cv.notify_one();
  });
  /* A timeout must not destroy a joinable thread or its shared state. */
  worker.detach();
  std::unique_lock<std::mutex> lock(state.mutex);
  if (!state.cv.wait_for(lock, std::chrono::seconds(3), [] { return state.done; }))
    return 8;
  if (state.value != 0x3576 || std::chrono::steady_clock::now() < before) return 9;
  return 0;
}
}

extern "C" int k7cxx_main(int argc, char **argv)
{
  if (argc != 1) {
    std::puts("usage: k7cxx (once per boot; no model or file access)");
    return 1;
  }
  (void)argv;
  if (started.exchange(true)) {
    std::puts("CXX already attempted; reboot required");
    return 1;
  }
  int result = 10;
  try { result = probe(); }
  catch (const std::exception &) { std::puts("CXX unexpected std::exception"); }
  catch (...) { std::puts("CXX unexpected exception"); }
  std::printf("CXX result=%s code=%d off_t_bits=%u pointer_bits=%u model_tested=0\n",
              result == 0 ? "PASS" : "FAIL", result,
              unsigned(sizeof(off_t) * 8), unsigned(sizeof(void *) * 8));
  return result;
}
