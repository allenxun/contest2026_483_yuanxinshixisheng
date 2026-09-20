#ifndef SHARED_RUNTIME_HPP
#define SHARED_RUNTIME_HPP
#include "onnxruntime_c_api.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <climits>
#ifndef SR_CAPACITY
#define SR_CAPACITY 4096
#endif
static_assert(SR_CAPACITY > 0 && SR_CAPACITY <= 4096, "bounded record capacity");
namespace sr_shared {
struct Port { void* ctx; void(*lock)(void*); void(*unlock)(void*); void*(*alloc)(size_t); void(*free)(void*); uintptr_t begin,end; };
class Lease;
class Runtime final {
 struct Record { void* p=nullptr; size_t n=0; bool model=false; };
 struct Adapter { OrtAllocator api; Runtime* owner; } adapter_{};
 const OrtApi* api_; Port port_; OrtEnv* env_=nullptr; OrtMemoryInfo* info_=nullptr;
 OrtEnv* attached_envs_[4]{}; size_t attached_env_count_=0;
 Record records_[SR_CAPACITY]{}; size_t leases_=0; bool own_env_=true;
 static void* ORT_API_CALL alloc_cb(OrtAllocator*a,size_t n){return reinterpret_cast<Adapter*>(a)->owner->allocate(n,false);}
 static void ORT_API_CALL free_cb(OrtAllocator*a,void*p){reinterpret_cast<Adapter*>(a)->owner->release(p,false);}
 static const OrtMemoryInfo* ORT_API_CALL info_cb(const OrtAllocator*a){return reinterpret_cast<const Adapter*>(a)->owner->info_;}
 void lock(){port_.lock(port_.ctx);} void unlock(){port_.unlock(port_.ctx);}
 friend class Lease;
 void* allocate(size_t n,bool model){lock();size_t i=0;void*p=nullptr;
  if(!env_||fault||!n){last_failure=1;goto fail;}
  if(n>limit-live){last_failure=2;goto fail;}
  while(i<SR_CAPACITY&&records_[i].p)++i;
  if(i==SR_CAPACITY){last_failure=3;goto fail;}
  p=port_.alloc(n);if(!p){last_failure=4;goto fail;}
  for(auto&r:records_)if(r.p==p){fault=true;goto bad;}
  if((reinterpret_cast<uintptr_t>(p)&63)||reinterpret_cast<uintptr_t>(p)<port_.begin||reinterpret_cast<uintptr_t>(p)>=port_.end||n>port_.end-reinterpret_cast<uintptr_t>(p)){fault=true;goto bad;}
  records_[i]={p,n,model};live+=n;++count;if(live>peak)peak=live;if(count>peak_count)peak_count=count;unlock();return p;
 bad:p=nullptr; // Invalid provider pointer retained; never guess a free.
 fail:failed_bytes=n;++failures;
  {
   const auto report_reason=last_failure;const auto report_live=live;
   const auto report_count=count;const auto report_peak=peak;
   const auto report_records=peak_count;const auto report_limit=limit;
   unlock();
   std::printf("SR_ALLOC_FAIL reason=%u request=%zu live=%zu count=%zu "
               "peak=%zu records=%zu quota=%zu\n",
               report_reason,n,report_live,report_count,report_peak,
               report_records,report_limit);
   std::fflush(stdout);
  }
  return nullptr;
 }
 void release(void*p,bool model){if(!p)return;lock();for(auto&r:records_)if(r.p==p){if(r.model!=model){fault=true;unlock();return;}port_.free(p);live-=r.n;--count;r={};unlock();return;}fault=true;unlock();}
 public:
 size_t limit,live=0,peak=0,count=0,peak_count=0,failures=0; bool fault=false;
 size_t failed_bytes=0; unsigned last_failure=0;
 Runtime(const OrtApi&api,Port port,size_t quota):api_(&api),port_(port),limit(quota){}
 Runtime(const Runtime&)=delete;Runtime&operator=(const Runtime&)=delete;
 // Stable address; successful init takes Env, failure leaves caller ownership.
 OrtStatus* init(OrtEnv*env){if(env_||!env||!port_.lock||!port_.unlock||!port_.alloc||!port_.free||port_.end<=port_.begin||!limit||limit>port_.end-port_.begin)return api_->CreateStatus(ORT_INVALID_ARGUMENT,"runtime config");
  auto*s=api_->CreateCpuMemoryInfo(OrtDeviceAllocator,OrtMemTypeDefault,&info_);if(s)return s;
  adapter_.api={ORT_API_VERSION,alloc_cb,free_cb,info_cb};adapter_.owner=this;
  s=api_->RegisterAllocator(env,&adapter_.api);if(s){api_->ReleaseMemoryInfo(info_);info_=nullptr;return s;}env_=env;return nullptr;
 }
 OrtAllocator* allocator(){return &adapter_.api;}
 // ASR and TTS construct separate Ort::Env wrappers. Both must use the same
 // allocator instance because the K7 model arena and allocation ledger are
 // process-wide. Register it once per distinct Env and reuse an existing
 // registration when ORT reports that the allocator is already present.
 OrtStatus* attach_borrowed(OrtEnv*env){
  if(!env||!port_.lock||!port_.unlock||!port_.alloc||!port_.free||
     port_.end<=port_.begin||!limit||limit>port_.end-port_.begin)
   return api_->CreateStatus(ORT_INVALID_ARGUMENT,"runtime config");
  for(size_t i=0;i<attached_env_count_;++i)if(attached_envs_[i]==env){
   std::printf("SR_ATTACH reused env=%p slots=%zu\n",env,attached_env_count_);
   std::fflush(stdout);return nullptr;
  }
  if(attached_env_count_==sizeof(attached_envs_)/sizeof(attached_envs_[0]))
   return api_->CreateStatus(ORT_FAIL,"runtime env capacity");
  if(!info_){
   auto*s=api_->CreateCpuMemoryInfo(OrtDeviceAllocator,OrtMemTypeDefault,&info_);
   if(s)return s;
   adapter_.api={ORT_API_VERSION,alloc_cb,free_cb,info_cb};adapter_.owner=this;
  }
  auto*s=api_->RegisterAllocator(env,&adapter_.api);
  if(s){
   const char*message=api_->GetErrorMessage(s);
   const bool duplicate=attached_env_count_&&message&&
    ::strstr(message,"allocator")&&
    (::strstr(message,"already")||::strstr(message,"registered"));
   std::printf("SR_ATTACH status=%s env=%p slots=%zu message=%s\n",
               duplicate?"duplicate-reused":"failed",env,
               attached_env_count_,message?message:"(null)");
   std::fflush(stdout);
   if(!duplicate)return s;
   api_->ReleaseStatus(s);s=nullptr;
  }
  if(!env_)env_=env;
  attached_envs_[attached_env_count_++]=env;own_env_=false;
  std::printf("SR_ATTACH registered env=%p slots=%zu\n",env,
              attached_env_count_);
  std::fflush(stdout);return nullptr;
 }
 // Caller must destroy borrowed Env before this Runtime, after Sessions.
 OrtStatus* init_borrowed(OrtEnv*env){return attach_borrowed(env);}
 // Owner excludes Run and external OrtValues; callbacks use supplied real lock.
 bool close(){if(leases_)return false;if(!env_)return !fault;
  lock();bool held=live||fault;unlock();if(held)return false;
  if(own_env_){api_->ReleaseEnv(env_);}env_=nullptr;attached_env_count_=0;
  lock();held=live||fault;unlock();if(held)return false;
  api_->ReleaseMemoryInfo(info_);info_=nullptr;return true;
 }
 ~Runtime(){if(!close())std::abort();} // Contract breach fail-stop, never dangling allocator.
};
class Lease final {
 Runtime&r_;void*bytes_=nullptr;size_t size_=0;OrtSession*session_=nullptr;
 public:
 explicit Lease(Runtime&r):r_(r){++r_.leases_;}
 Lease(const Lease&)=delete;Lease&operator=(const Lease&)=delete;
 void* reserve(size_t n){if(bytes_||session_||!n||n>INT_MAX)return nullptr;bytes_=r_.allocate(n,true);if(bytes_)size_=n;return bytes_;}
 // Caller must fill exact persistent bytes and verify format/length/hash first.
 OrtStatus* load_verified(OrtSessionOptions*options){auto*a=r_.api_;if(!bytes_||session_||!r_.env_||r_.fault)return a->CreateStatus(ORT_INVALID_ARGUMENT,"lease not ready");
  OrtStatus*s=a->SetIntraOpNumThreads(options,1);if(s)return s;
  s=a->SetInterOpNumThreads(options,1);if(s)return s;
  s=a->SetSessionGraphOptimizationLevel(options,ORT_DISABLE_ALL);if(s)return s;
  const char*keys[]={"session.use_env_allocators","session.load_model_format","session.use_ort_model_bytes_directly","session.use_ort_model_bytes_for_initializers"};
  for(unsigned i=0;i<4;++i){s=a->AddSessionConfigEntry(options,keys[i],i==1?"ORT":"1");if(s)return s;}
  return a->CreateSessionFromArray(r_.env_,bytes_,size_,options,&session_);
 }
 OrtSession* session()const{return session_;}
 void close(){if(session_){r_.api_->ReleaseSession(session_);session_=nullptr;}if(bytes_){r_.release(bytes_,true);bytes_=nullptr;size_=0;}}
 ~Lease(){close();--r_.leases_;}
};
}
#endif
