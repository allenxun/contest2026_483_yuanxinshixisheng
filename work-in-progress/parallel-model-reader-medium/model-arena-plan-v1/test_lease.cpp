#include "arena_buffer_lease.h"
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <cstring>
struct Fake {alignas(64) unsigned char bytes[256];int gets=0,frees=0,live=0;bool fail=false,misalign=false;};
static void *take(void *p,size_t n){Fake *f=(Fake*)p;++f->gets;if(f->fail||n>256)return nullptr;f->live=1;return f->bytes+(f->misalign?1:0);}
static void release(void *p,void *q){Fake *f=(Fake*)p;if(q!=f->bytes+(f->misalign?1:0)||!f->live)std::abort();f->live=0;++f->frees;}
#define CHECK(x) do{if(!(x)){std::fprintf(stderr,"FAIL %d %s\n",__LINE__,#x);return 1;}}while(0)
int main(){Fake f;arena_source source{&f,take,release};arena_lease l=ARENA_LEASE_INIT;
 CHECK(arena_lease_open(&l,source,257,256)==EINVAL && f.gets==0);
 f.fail=true;CHECK(arena_lease_open(&l,source,64,256)==ENOMEM && !f.live && !l.view);f.fail=false;
 f.misalign=true;CHECK(arena_lease_open(&l,source,64,256)==EINVAL && !f.live && f.frees==1);f.misalign=false;
 CHECK(arena_lease_open(&l,source,64,256)==0 && f.live && ggml_backend_buffer_is_host(l.view));
 CHECK(ggml_backend_buffer_get_base(l.view)==f.bytes);
 ggml_backend_buffer_clear(l.view,0x5a);for(int i=0;i<64;++i)CHECK(f.bytes[i]==0x5a);
 CHECK(arena_lease_open(&l,source,64,256)==EBUSY);
 arena_lease_close(&l);CHECK(!f.live && f.frees==2 && !l.view && !l.memory);
 arena_lease_close(&l);CHECK(f.frees==2);
 std::puts("PASS real ggml borrowed-buffer wrapper; mock arena provider only; budget/fail/alignment/pairing/idempotence");return 0;
}

