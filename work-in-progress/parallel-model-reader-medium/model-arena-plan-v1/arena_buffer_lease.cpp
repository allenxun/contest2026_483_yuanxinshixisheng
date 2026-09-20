#include "arena_buffer_lease.h"
#include <cerrno>
#include <cstdint>
#include <new>
extern "C" int arena_lease_open(arena_lease *l,arena_source source,size_t bytes,size_t budget) {
    if(!l || !source.alloc || !source.release || !bytes || bytes>budget)return EINVAL;
    if(l->memory || l->view)return EBUSY;
    void *p=source.alloc(source.ctx,bytes);if(!p)return ENOMEM;
    const size_t alignment=ggml_backend_buft_get_alignment(ggml_backend_cpu_buffer_type());
    if(!alignment || reinterpret_cast<uintptr_t>(p)%alignment) {source.release(source.ctx,p);return EINVAL;}
    ggml_backend_buffer_t view=nullptr;
    try {view=ggml_backend_cpu_buffer_from_ptr(p,bytes);}
    catch(const std::bad_alloc &) {source.release(source.ctx,p);return ENOMEM;}
    catch(...) {source.release(source.ctx,p);return EIO;}
    if(!view){source.release(source.ctx,p);return ENOMEM;}
    l->source=source;l->memory=p;l->view=view;return 0;
}
extern "C" void arena_lease_close(arena_lease *l) {
    if(!l)return;
    /* from_ptr owns only wrapper; its free_buffer is NULL in fixed b5046. */
    if(l->view)ggml_backend_buffer_free(l->view);
    if(l->memory)l->source.release(l->source.ctx,l->memory);
    *l=arena_lease ARENA_LEASE_INIT;
}
