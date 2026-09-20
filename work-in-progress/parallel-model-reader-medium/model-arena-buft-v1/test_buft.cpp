#include "k7_host_buft.h"
#include "ggml-alloc.h"
#include "ggml-cpu.h"
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
struct fake_arena {
    alignas(4096) unsigned char slots[8][256]{};
    bool live[8]{};size_t sizes[8]{};void *returns[8]{};
    unsigned calls=0,releases=0,fail_at=0;bool misalign=false;
};
static void *allocate(void *ctx,size_t bytes,size_t alignment) {
    auto *a=static_cast<fake_arena*>(ctx);++a->calls;
    if(a->calls==a->fail_at || bytes>256)return nullptr;
    for(unsigned i=0;i<8;++i)if(!a->live[i]) {
        if(reinterpret_cast<uintptr_t>(a->slots[i])%alignment)return nullptr;
        a->live[i]=true;a->sizes[i]=bytes;a->returns[i]=a->slots[i]+(a->misalign?1:0);return a->returns[i];
    }
    return nullptr;
}
static void release(void *ctx,void *p,size_t bytes) {
    auto *a=static_cast<fake_arena*>(ctx);
    for(unsigned i=0;i<8;++i)if(a->live[i] && a->returns[i]==p && a->sizes[i]==bytes){a->live[i]=false;++a->releases;return;}
    std::abort(); // wrong pointer/size/double release is a test failure
}
static unsigned live(const fake_arena &a){unsigned n=0;for(bool b:a.live)n+=b;return n;}
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static k7_buft_config config(fake_arena &a,size_t max=256,size_t budget=384) {return {{&a,allocate,release},64,max,budget};}
static int direct(void) {
    fake_arena a;k7_buft_config c=config(a);ggml_backend_buffer_type_t type=nullptr;k7_buft_stats stats{};size_t n=7;
    CHECK(k7_buft_round_bytes(SIZE_MAX,64,&n)==EOVERFLOW && n==7);
    CHECK(k7_buft_round_bytes(65,64,&n)==0 && n==128);
    CHECK(k7_buft_round_bytes(1,3,&n)==EINVAL);
    CHECK(k7_buft_round_bytes(1,8192,&n)==EINVAL);
    c.alignment=ggml_backend_buft_get_alignment(ggml_backend_cpu_buffer_type())/2;CHECK(k7_buft_create(&c,&type)==EINVAL && !type);c=config(a);
    CHECK(k7_buft_create(&c,&type)==0);
    CHECK(!std::strcmp(ggml_backend_buft_name(type),"K7_ARENA_HOST") && ggml_backend_buft_is_host(type));
    CHECK(ggml_backend_buft_get_alignment(type)==64 && ggml_backend_buft_get_max_size(type)==256);
    auto *backend=ggml_backend_cpu_init();CHECK(backend && ggml_backend_supports_buft(backend,type));ggml_backend_free(backend);
    CHECK(!ggml_backend_buft_alloc_buffer(type,SIZE_MAX));CHECK(k7_buft_get_stats(type,&stats)==0 && stats.last_error==EOVERFLOW && a.calls==0);
    auto b1=ggml_backend_buft_alloc_buffer(type,65);auto b2=ggml_backend_buft_alloc_buffer(type,129);
    CHECK(b1 && b2 && ggml_backend_buffer_get_type(b1)==type && live(a)==2);
    CHECK(k7_buft_get_stats(type,&stats)==0 && stats.live_bytes==320 && stats.live_buffers==2);
    CHECK(!ggml_backend_buft_alloc_buffer(type,65) && a.calls==2);
    CHECK(k7_buft_destroy(&type)==EBUSY && type);
    ggml_backend_buffer_clear(b1,0x5a);CHECK(static_cast<unsigned char*>(ggml_backend_buffer_get_base(b1))[64]==0x5a);
    ggml_backend_buffer_free(b2);ggml_backend_buffer_free(b1);
    CHECK(k7_buft_get_stats(type,&stats)==0 && !stats.live_bytes && !stats.live_buffers && stats.peak_bytes==320 && !live(a) && a.releases==2);
    auto zero=ggml_backend_buft_alloc_buffer(type,0);CHECK(zero && a.calls==2);
    ggml_backend_buffer_free(zero); // upstream dummy bypasses provider; free before type
    CHECK(k7_buft_destroy(&type)==0 && !type && k7_buft_destroy(&type)==0);
    std::puts("PASS direct real buft: CPU host support, overflow, padding budget, two buffers, busy owner, zero dummy");return 0;
}
static int faults(void) {
    fake_arena a;auto c=config(a);ggml_backend_buffer_type_t type=nullptr;k7_buft_stats stats{};
    CHECK(k7_buft_create(&c,&type)==0);a.fail_at=1;
    CHECK(!ggml_backend_buft_alloc_buffer(type,64) && !live(a) && a.releases==0);
    a.fail_at=0;a.misalign=true;
    CHECK(!ggml_backend_buft_alloc_buffer(type,64) && !live(a) && a.releases==1);a.misalign=false;
#ifdef K7_BUFT_TESTING
    CHECK(k7_buft_test_fail_next_wrapper(type)==0);
    CHECK(!ggml_backend_buft_alloc_buffer(type,64) && !live(a) && a.releases==2);
#endif
    CHECK(k7_buft_get_stats(type,&stats)==0 && !stats.live_buffers && !stats.live_bytes);
    auto buf=ggml_backend_buft_alloc_buffer(type,64);CHECK(buf);ggml_backend_buffer_free(buf);
    CHECK(!live(a) && k7_buft_destroy(&type)==0);
    std::puts("PASS provider OOM/misalignment + test-build wrapper exception rollback, then recovery");return 0;
}
static int tensors(unsigned fail_at,size_t budget) {
    fake_arena a;auto c=config(a,128,budget);ggml_backend_buffer_type_t type=nullptr;
    CHECK(k7_buft_create(&c,&type)==0);a.fail_at=fail_at;
    alignas(64) unsigned char metadata[16384];
    auto *ctx=ggml_init({sizeof(metadata),metadata,true});CHECK(ctx);
    ggml_tensor *t[3];for(unsigned i=0;i<3;++i)t[i]=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,32);
    auto buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,type);
    if(fail_at || budget<384) {
        CHECK(!buffer && !live(a));
        // ggml may leave stale tensor data after partial failure: discard context.
        ggml_free(ctx);CHECK(k7_buft_destroy(&type)==0);
        std::printf("PASS real ctx multi-buffer partial rollback fail_at=%u budget=%zu\n",fail_at,budget);return 0;
    }
    CHECK(buffer && live(a)==3);
    float in[32],out[32];for(unsigned i=0;i<32;++i)in[i]=static_cast<float>(i)-10;
    for(unsigned i=0;i<3;++i) {
        CHECK(ggml_backend_buffer_get_type(t[i]->buffer)==type);
        ggml_backend_tensor_set(t[i],in,0,sizeof(in));ggml_backend_tensor_get(t[i],out,0,sizeof(out));
        CHECK(!std::memcmp(in,out,sizeof(in)));
    }
    ggml_backend_buffer_free(buffer);ggml_free(ctx);
    CHECK(!live(a) && a.releases==3);k7_buft_stats stats{};
    CHECK(k7_buft_get_stats(type,&stats)==0 && stats.live_bytes==0 && stats.live_buffers==0);
    CHECK(k7_buft_destroy(&type)==0);
    std::puts("PASS real ggml context: three tensor buffers, set/get, aggregate free and zero ownership");return 0;
}
int main(){CHECK(direct()==0);CHECK(faults()==0);CHECK(tensors(0,512)==0);CHECK(tensors(2,512)==0);CHECK(tensors(0,256)==0);return 0;}

