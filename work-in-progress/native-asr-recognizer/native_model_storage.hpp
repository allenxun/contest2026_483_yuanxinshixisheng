#pragma once
#define SR_CAPACITY 2048
#include "shared_runtime.hpp"
#include "k7_model_arena.h"
#include <pthread.h>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <nuttx/config.h>
#if defined(CONFIG_MM_FILL_ALLOCATIONS) || defined(CONFIG_MM_KASAN)
#error "Re-audit staged model memory before enabling heap fill or KASAN"
#endif
extern "C" {
#include "sha256_namespace.h"
}

namespace k7_asr {
class ModelStorage {
  pthread_mutex_t mutex_ = PTHREAD_MUTEX_INITIALIZER;
  static void lock(void *p) { if(pthread_mutex_lock(&static_cast<ModelStorage*>(p)->mutex_))std::abort(); }
  static void unlock(void *p) { if(pthread_mutex_unlock(&static_cast<ModelStorage*>(p)->mutex_))std::abort(); }
  static bool hash(const void*data,size_t bytes,const unsigned char*expected) {
    sha256_t ctx;unsigned char digest[32];sha256_init(&ctx);
    for(size_t i=0;i<bytes;) {size_t n=bytes-i;if(n>4096)n=4096;sha256_update(&ctx,static_cast<const unsigned char*>(data)+i,n);i+=n;}
    sha256_final(&ctx,digest);return !std::memcmp(digest,expected,32);
  }
  static void check(OrtStatus*s) {
    if(!s)return;
    const auto*a=OrtGetApiBase()->GetApi(ORT_API_VERSION);
    std::string message=a->GetErrorMessage(s);a->ReleaseStatus(s);throw std::runtime_error(message);
  }
 public:
  sr::Runtime runtime;
  sr::Lease encoder,decoder;
  void *encoder_bytes=nullptr,*decoder_bytes=nullptr;
  static constexpr size_t encoder_size=166189616,decoder_size=72024848;
  ModelStorage():runtime(*OrtGetApiBase()->GetApi(ORT_API_VERSION),
    sr::Port{this,lock,unlock,k7_model_alloc,k7_model_free,K7_MODEL_ARENA_BASE,K7_MODEL_ARENA_BASE+K7_MODEL_ARENA_SIZE},
    768u*1024u*1024u),encoder(runtime),decoder(runtime) {}
  // Declared BEFORE Ort::Env by owner: Env destructs before this allocator.
  ~ModelStorage() {
    decoder.close();encoder.close();
    std::printf("ASR_STORAGE peak=%zu live=%zu records=%zu failures=%zu reason=%u\n",
      runtime.peak,runtime.live,runtime.peak_count,runtime.failures,runtime.last_failure);
  }
  void initialize(OrtEnv*env,OrtSessionOptions*options) {
    static const unsigned char enc[32]={248,31,158,101,110,33,188,108,131,80,183,160,78,53,99,190,227,85,45,208,224,71,164,75,94,156,151,143,209,136,193,175};
    static const unsigned char dec[32]={15,88,202,75,215,119,40,216,229,18,184,82,239,245,142,154,238,221,144,207,162,1,106,228,3,121,180,112,10,120,218,20};
    const void*source_enc=reinterpret_cast<const void*>(0x80000000);
    const void*source_dec=reinterpret_cast<const void*>(0x90000000);
    if(!hash(source_enc,encoder_size,enc)||!hash(source_dec,decoder_size,dec))throw std::runtime_error("ASR staged model hash");
    if(k7_model_arena_initialize())throw std::runtime_error("ASR model arena");
    check(runtime.init_borrowed(env));
    encoder_bytes=encoder.reserve(encoder_size);decoder_bytes=decoder.reserve(decoder_size);
    if(!encoder_bytes||!decoder_bytes)throw std::runtime_error("ASR model reservation");
    for(auto pair:{std::pair<void*,size_t>{encoder_bytes,encoder_size},{decoder_bytes,decoder_size}}) {
      uintptr_t p=reinterpret_cast<uintptr_t>(pair.first);
      if(p>=0x80000000||pair.second>0x80000000-p)throw std::runtime_error("ASR staging overlap");
    }
    std::memcpy(encoder_bytes,source_enc,encoder_size);std::memcpy(decoder_bytes,source_dec,decoder_size);
    if(!hash(encoder_bytes,encoder_size,enc)||!hash(decoder_bytes,decoder_size,dec))throw std::runtime_error("ASR persistent model hash");
    const auto*a=OrtGetApiBase()->GetApi(ORT_API_VERSION);
    check(a->SetSessionExecutionMode(options,ORT_SEQUENTIAL));
    check(a->SetIntraOpNumThreads(options,1));check(a->SetInterOpNumThreads(options,1));
    check(a->SetSessionGraphOptimizationLevel(options,ORT_DISABLE_ALL));
    const char*keys[]={"session.use_env_allocators","session.load_model_format","session.use_ort_model_bytes_directly","session.use_ort_model_bytes_for_initializers"};
    for(unsigned i=0;i<4;i++)check(a->AddSessionConfigEntry(options,keys[i],i==1?"ORT":"1"));
  }
};
}
