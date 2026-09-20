#include "native_tts_model_storage.hpp"

#include <cassert>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>
#include <windows.h>

namespace {

OrtApi api{};
OrtApiBase api_base{};
OrtAllocator *registered_allocator = nullptr;
std::vector<std::string> calls;
std::map<std::string, std::string> entries;

OrtStatus *ORT_API_CALL create_status(OrtErrorCode, const char *) noexcept {
  return reinterpret_cast<OrtStatus *>(1);
}

OrtStatus *ORT_API_CALL create_memory_info(OrtAllocatorType, OrtMemType,
                                            OrtMemoryInfo **out) noexcept {
  *out = reinterpret_cast<OrtMemoryInfo *>(2);
  calls.emplace_back("memory-info");
  return nullptr;
}

OrtStatus *ORT_API_CALL register_allocator(OrtEnv *, OrtAllocator *allocator)
    noexcept {
  registered_allocator = allocator;
  calls.emplace_back("register-allocator");
  return nullptr;
}

void ORT_API_CALL release_memory_info(OrtMemoryInfo *) noexcept {
  calls.emplace_back("release-memory-info");
}

const char *ORT_API_CALL get_error_message(const OrtStatus *) noexcept {
  return "test status";
}

void ORT_API_CALL release_status(OrtStatus *) noexcept {}

OrtStatus *ORT_API_CALL set_execution(OrtSessionOptions *, ExecutionMode mode)
    noexcept {
  assert(mode == ORT_SEQUENTIAL);
  calls.emplace_back("sequential");
  return nullptr;
}

OrtStatus *ORT_API_CALL set_intra(OrtSessionOptions *, int threads) noexcept {
  assert(threads == 1);
  calls.emplace_back("intra-1");
  return nullptr;
}

OrtStatus *ORT_API_CALL set_inter(OrtSessionOptions *, int threads) noexcept {
  assert(threads == 1);
  calls.emplace_back("inter-1");
  return nullptr;
}

OrtStatus *ORT_API_CALL set_optimization(OrtSessionOptions *,
                                         GraphOptimizationLevel level) noexcept {
  assert(level == ORT_DISABLE_ALL);
  calls.emplace_back("optimization-off");
  return nullptr;
}

OrtStatus *ORT_API_CALL disable_pattern(OrtSessionOptions *) noexcept {
  calls.emplace_back("memory-pattern-off");
  return nullptr;
}

OrtStatus *ORT_API_CALL add_entry(OrtSessionOptions *, const char *key,
                                   const char *value) noexcept {
  entries[key] = value;
  return nullptr;
}

const OrtApi *ORT_API_CALL get_api(uint32_t version) noexcept {
  assert(version == ORT_API_VERSION);
  return &api;
}

const char *ORT_API_CALL get_version() noexcept { return "test"; }

}  // namespace

extern "C" const OrtApiBase *ORT_API_CALL OrtGetApiBase(void) noexcept {
  return &api_base;
}

extern "C" int k7_model_arena_initialize(void) { return 0; }

extern "C" void *k7_model_alloc(size_t bytes) {
  static uintptr_t next = 0x61000000;
  void *memory = VirtualAlloc(reinterpret_cast<void *>(next), bytes,
                              MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
  if (memory) next += 0x10000;
  return memory;
}

extern "C" void k7_model_free(void *memory) {
  assert(VirtualFree(memory, 0, MEM_RELEASE));
}

int main() {
  api.CreateStatus = create_status;
  api.CreateCpuMemoryInfo = create_memory_info;
  api.RegisterAllocator = register_allocator;
  api.ReleaseMemoryInfo = release_memory_info;
  api.GetErrorMessage = get_error_message;
  api.ReleaseStatus = release_status;
  api.SetSessionExecutionMode = set_execution;
  api.SetIntraOpNumThreads = set_intra;
  api.SetInterOpNumThreads = set_inter;
  api.SetSessionGraphOptimizationLevel = set_optimization;
  api.DisableMemPattern = disable_pattern;
  api.AddSessionConfigEntry = add_entry;
  api_base.GetApi = get_api;
  api_base.GetVersionString = get_version;

  {
    k7_tts_storage::ModelStorage storage;
    storage.initialize(reinterpret_cast<OrtEnv *>(3),
                       reinterpret_cast<OrtSessionOptions *>(4),
                       "/mnt/k7tts/vits.ort");
    assert(storage.model_data() == reinterpret_cast<const void *>(0x96000730));
    assert(registered_allocator);
    void *first = registered_allocator->Alloc(registered_allocator, 4096);
    void *second = registered_allocator->Alloc(registered_allocator, 8192);
    assert(first && second && storage.runtime.peak == 12288 &&
           storage.runtime.peak_count == 2);
    registered_allocator->Free(registered_allocator, second);
    registered_allocator->Free(registered_allocator, first);
    assert(storage.runtime.live == 0 && storage.runtime.count == 0);
  }

  assert(entries.size() == 4);
  assert(entries["session.use_env_allocators"] == "1");
  assert(entries["session.load_model_format"] == "ORT");
  assert(entries["session.use_ort_model_bytes_directly"] == "1");
  assert(entries["session.use_ort_model_bytes_for_initializers"] == "1");
  assert(calls.size() == 8);
  assert(calls.back() == "release-memory-info");

  bool rejected = false;
  try {
    k7_tts_storage::ModelStorage storage;
    storage.initialize(reinterpret_cast<OrtEnv *>(3),
                       reinterpret_cast<OrtSessionOptions *>(4),
                       "/tmp/unverified.ort");
  } catch (const std::runtime_error &) {
    rejected = true;
  }
  assert(rejected);
  return 0;
}
