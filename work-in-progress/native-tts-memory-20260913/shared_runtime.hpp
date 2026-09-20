#ifndef K7_TTS_SHARED_RUNTIME_HPP
#define K7_TTS_SHARED_RUNTIME_HPP

#include "onnxruntime_c_api.h"

#include <cstdint>
#include <cstdlib>

#ifndef K7_TTS_ORT_ALLOCATION_CAPACITY
#define K7_TTS_ORT_ALLOCATION_CAPACITY 2048
#endif

static_assert(K7_TTS_ORT_ALLOCATION_CAPACITY > 0 &&
                  K7_TTS_ORT_ALLOCATION_CAPACITY <= 4096,
              "bounded ORT allocation record capacity");

namespace k7_tts_storage {

struct Port {
  void *context;
  void (*lock)(void *);
  void (*unlock)(void *);
  void *(*allocate)(size_t);
  void (*release)(void *);
  uintptr_t begin;
  uintptr_t end;
};

class Runtime final {
  struct Record {
    void *pointer = nullptr;
    size_t bytes = 0;
  };

  struct Adapter {
    OrtAllocator api;
    Runtime *owner;
  } adapter_{};

  const OrtApi *api_;
  Port port_;
  OrtEnv *env_ = nullptr;
  OrtMemoryInfo *info_ = nullptr;
  Record records_[K7_TTS_ORT_ALLOCATION_CAPACITY]{};

  static void *ORT_API_CALL allocate_callback(OrtAllocator *allocator,
                                               size_t bytes) {
    return reinterpret_cast<Adapter *>(allocator)->owner->allocate(bytes);
  }

  static void ORT_API_CALL release_callback(OrtAllocator *allocator,
                                             void *pointer) {
    reinterpret_cast<Adapter *>(allocator)->owner->release(pointer);
  }

  static const OrtMemoryInfo *ORT_API_CALL info_callback(
      const OrtAllocator *allocator) {
    return reinterpret_cast<const Adapter *>(allocator)->owner->info_;
  }

  void lock() { port_.lock(port_.context); }
  void unlock() { port_.unlock(port_.context); }

  void *allocate(size_t bytes) {
    lock();
    size_t slot = 0;
    void *pointer = nullptr;
    uintptr_t address = 0;
    if (!env_ || fault || !bytes) {
      last_failure = 1;
      goto failed;
    }
    if (bytes > limit - live) {
      last_failure = 2;
      goto failed;
    }
    while (slot < K7_TTS_ORT_ALLOCATION_CAPACITY && records_[slot].pointer) {
      ++slot;
    }
    if (slot == K7_TTS_ORT_ALLOCATION_CAPACITY) {
      last_failure = 3;
      goto failed;
    }
    pointer = port_.allocate(bytes);
    if (!pointer) {
      last_failure = 4;
      goto failed;
    }
    for (const auto &record : records_) {
      if (record.pointer == pointer) {
        fault = true;
        last_failure = 5;
        pointer = nullptr;
        goto failed;
      }
    }
    address = reinterpret_cast<uintptr_t>(pointer);
    if ((address & 63u) || address < port_.begin || address >= port_.end ||
        bytes > port_.end - address) {
      fault = true;
      last_failure = 6;
      port_.release(pointer);
      pointer = nullptr;
      goto failed;
    }
    records_[slot].pointer = pointer;
    records_[slot].bytes = bytes;
    live += bytes;
    ++count;
    if (live > peak) peak = live;
    if (count > peak_count) peak_count = count;
    unlock();
    return pointer;

  failed:
    failed_bytes = bytes;
    ++failures;
    unlock();
    return nullptr;
  }

  void release(void *pointer) {
    if (!pointer) return;
    lock();
    for (auto &record : records_) {
      if (record.pointer == pointer) {
        port_.release(pointer);
        live -= record.bytes;
        --count;
        record = {};
        unlock();
        return;
      }
    }
    fault = true;
    unlock();
  }

 public:
  size_t limit;
  size_t live = 0;
  size_t peak = 0;
  size_t count = 0;
  size_t peak_count = 0;
  size_t failures = 0;
  size_t failed_bytes = 0;
  unsigned last_failure = 0;
  bool fault = false;

  Runtime(const OrtApi &api, Port port, size_t quota)
      : api_(&api), port_(port), limit(quota) {}
  Runtime(const Runtime &) = delete;
  Runtime &operator=(const Runtime &) = delete;

  OrtStatus *initialize_borrowed(OrtEnv *env) {
    if (env_ || !env || !port_.lock || !port_.unlock || !port_.allocate ||
        !port_.release || port_.end <= port_.begin || !limit ||
        limit > port_.end - port_.begin) {
      return api_->CreateStatus(ORT_INVALID_ARGUMENT, "TTS allocator config");
    }
    OrtStatus *status = api_->CreateCpuMemoryInfo(
        OrtDeviceAllocator, OrtMemTypeDefault, &info_);
    if (status) return status;
    adapter_.api.version = ORT_API_VERSION;
    adapter_.api.Alloc = allocate_callback;
    adapter_.api.Free = release_callback;
    adapter_.api.Info = info_callback;
    adapter_.owner = this;
    status = api_->RegisterAllocator(env, &adapter_.api);
    if (status) {
      api_->ReleaseMemoryInfo(info_);
      info_ = nullptr;
      return status;
    }
    env_ = env;
    return nullptr;
  }

  bool close_after_env() {
    if (!env_) return !fault;
    lock();
    const bool held = live || fault;
    unlock();
    if (held) return false;
    // Ort::Env is declared after this object and is therefore already gone.
    env_ = nullptr;
    api_->ReleaseMemoryInfo(info_);
    info_ = nullptr;
    return true;
  }

  ~Runtime() {
    if (!close_after_env()) std::abort();
  }
};

}  // namespace k7_tts_storage

#endif
