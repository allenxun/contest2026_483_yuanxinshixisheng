#include "shared_runtime.hpp"
#include <cassert>
#include <cstdio>
#include <stdexcept>
namespace {
int env_releases=0,info_releases=0,fail_register=0;
OrtAllocator*registered=nullptr;
alignas(64) unsigned char pool[4096];
void noop(void*){}
void*allocate(size_t n){return n<=sizeof(pool)?pool:nullptr;}
void release(void*p){assert(p==pool);}
OrtStatus*ORT_API_CALL memory(OrtAllocatorType,OrtMemType,OrtMemoryInfo**out) noexcept {*out=reinterpret_cast<OrtMemoryInfo*>(2);return nullptr;}
OrtStatus*ORT_API_CALL reg(OrtEnv*,OrtAllocator*a) noexcept {registered=a;return fail_register?reinterpret_cast<OrtStatus*>(3):nullptr;}
void ORT_API_CALL env(OrtEnv*){assert(registered->Info(registered)==reinterpret_cast<OrtMemoryInfo*>(2));++env_releases;}
void ORT_API_CALL info(OrtMemoryInfo*){++info_releases;}
OrtStatus*ORT_API_CALL status(OrtErrorCode,const char*) noexcept {return reinterpret_cast<OrtStatus*>(3);}
OrtApi api{};
sr::Port port(){return {nullptr,noop,noop,allocate,release,reinterpret_cast<uintptr_t>(pool),reinterpret_cast<uintptr_t>(pool)+sizeof(pool)};}
void reset(){env_releases=info_releases=fail_register=0;registered=nullptr;}
struct BorrowedOwner {
 sr::Runtime runtime{api,port(),4096};
 struct Env {~Env(){env(reinterpret_cast<OrtEnv*>(1));}} owner_env;
 // Models/sessions destruct before Env, which destructs before Runtime.
 sr::Lease model{runtime};
 BorrowedOwner(bool fail){assert(!runtime.init_borrowed(reinterpret_cast<OrtEnv*>(1)));assert(model.reserve(128));if(fail)throw std::runtime_error("construction fault");}
};
}
int main(){
 api.CreateCpuMemoryInfo=memory;api.RegisterAllocator=reg;api.ReleaseEnv=env;api.ReleaseMemoryInfo=info;api.CreateStatus=status;
 reset();{sr::Runtime r(api,port(),4096);assert(!r.init(reinterpret_cast<OrtEnv*>(1)));}assert(env_releases==1&&info_releases==1);
 reset();{BorrowedOwner r(false);}assert(env_releases==1&&info_releases==1);
 reset();try{BorrowedOwner r(true);}catch(const std::runtime_error&){}assert(env_releases==1&&info_releases==1);
 reset();fail_register=1;{sr::Runtime r(api,port(),4096);assert(r.init_borrowed(reinterpret_cast<OrtEnv*>(1)));}assert(env_releases==0&&info_releases==1);
 std::puts("PASS owned, borrowed, constructor-unwind, registration-failure ownership (4 scenarios)");
}
