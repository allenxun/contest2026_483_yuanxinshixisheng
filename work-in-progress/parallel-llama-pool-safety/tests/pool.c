#include "ggml-pool-safe.h"
#include "ggml-backend.h"
#include "ggml-alloc.h"
#include <stdatomic.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
static unsigned checks,cases;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"failed_line=%d\n",__LINE__);abort();}}while(0)
struct witness {
    atomic_long bytes,mutexes,conds,attrs,handles,running;
    atomic_uint compute_mask,starts,exits;
    enum ggml_pool_site site;unsigned ordinal;
    bool join_fail;
};
static int fault(void *p,enum ggml_pool_site s,unsigned i) {
    struct witness *w=p;return (s==w->site && i==w->ordinal) || (s==THREAD_JOIN && w->join_fail);
}
static void note(void *p,enum ggml_pool_resource r,int delta,size_t n) {
    struct witness *w=p;
    switch(r) {
    case POOL_BYTES:atomic_fetch_add(&w->bytes,(long)n*delta);break;
    case POOL_MUTEX:atomic_fetch_add(&w->mutexes,delta);break;
    case POOL_COND:atomic_fetch_add(&w->conds,delta);break;
    case POOL_ATTR:atomic_fetch_add(&w->attrs,delta);break;
    case POOL_THREAD:atomic_fetch_add(&w->handles,delta);break;
    case POOL_RUNNING:
        atomic_fetch_add(&w->running,delta);
        if(delta>0)atomic_fetch_add(&w->starts,1);else atomic_fetch_add(&w->exits,1);
        break;
    case POOL_COMPUTE:atomic_fetch_or(&w->compute_mask,1u<<(unsigned)n);break;
    }
}
static struct ggml_pool_options options(struct witness *w) {
    *w=(struct witness){0};
    atomic_init(&w->bytes,0);atomic_init(&w->mutexes,0);atomic_init(&w->conds,0);
    atomic_init(&w->attrs,0);atomic_init(&w->handles,0);atomic_init(&w->running,0);
    atomic_init(&w->compute_mask,0);atomic_init(&w->starts,0);atomic_init(&w->exits,0);
    struct ggml_pool_options o=ggml_pool_options_default();o.hooks=(struct ggml_pool_hooks){w,fault,note};return o;
}
static void zero(struct witness *w) {
    CHECK(atomic_load(&w->bytes)==0);CHECK(atomic_load(&w->mutexes)==0);
    CHECK(atomic_load(&w->conds)==0);CHECK(atomic_load(&w->attrs)==0);
    CHECK(atomic_load(&w->handles)==0);CHECK(atomic_load(&w->running)==0);
    CHECK(atomic_load(&w->starts)==atomic_load(&w->exits));
}
static void graph(struct ggml_threadpool *pool,int threads,struct witness *w) {
    ggml_backend_t backend=ggml_backend_cpu_init();CHECK(backend);
    ggml_backend_cpu_set_n_threads(backend,threads);ggml_backend_cpu_set_threadpool(backend,pool);
    struct ggml_init_params ip={1024*1024,NULL,true};struct ggml_context *ctx=ggml_init(ip);CHECK(ctx);
    struct ggml_tensor *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,64,64);
    /* MUL (not SQR/SUM) uses n_threads and partitions 64 rows. */
    struct ggml_tensor *y=ggml_mul(ctx,x,x);
    struct ggml_cgraph *g=ggml_new_graph(ctx);ggml_build_forward_expand(g,y);
    ggml_backend_buffer_t buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);CHECK(buffer);
    float data[4096];for(int i=0;i<4096;i++)data[i]=2;
    ggml_backend_tensor_set(x,data,0,sizeof(data));
    enum ggml_status result=ggml_backend_graph_compute(backend,g);
    if(!pool && threads>4){CHECK(result==GGML_STATUS_ALLOC_FAILED);goto cleanup;}
    CHECK(result==GGML_STATUS_SUCCESS);
    ggml_backend_tensor_get(y,data,0,sizeof(data));
    for(int i=0;i<4096;i++){CHECK(data[i]==4);}
    if(w)CHECK(atomic_load(&w->compute_mask)==((1u<<(unsigned)threads)-2u));
cleanup:
    ggml_backend_buffer_free(buffer);ggml_free(ctx);ggml_backend_free(backend);
}
static void good(struct witness *w,struct ggml_pool_options *o,int threads,bool paused) {
    struct ggml_threadpool_params p=ggml_threadpool_params_default(threads);p.poll=0;p.paused=paused;
    struct ggml_threadpool *t=NULL;w->site=0;w->join_fail=false;atomic_store(&w->compute_mask,0);
    unsigned before=atomic_load(&w->starts);
    CHECK(ggml_pool_create_checked(&p,o,&t)==0 && t);
    graph(t,threads,w);CHECK(ggml_pool_destroy_checked(&t)==0 && !t);zero(w);
    CHECK(atomic_load(&w->starts)==before+(unsigned)threads-1);cases++;
}
int main(void) {
    ggml_cpu_init();
    for(int threads=2;threads<=4;threads+=2)for(unsigned pause=0;pause<2;pause++) {
        for(int site=POOL_ALLOC;site<=THREAD_CREATE;site++) {
            unsigned count=site==THREAD_CREATE?(unsigned)threads-1:1;
            for(unsigned i=1;i<=count;i++) {
                struct witness w;struct ggml_pool_options o=options(&w);
                struct ggml_threadpool_params p=ggml_threadpool_params_default(threads);p.paused=pause!=0;p.poll=0;
                w.site=(enum ggml_pool_site)site;w.ordinal=i;
                struct ggml_threadpool *t=NULL;CHECK(ggml_pool_create_checked(&p,&o,&t)!=0 && !t);
                CHECK(atomic_load(&w.starts)==(site==THREAD_CREATE?i-1:0));
                zero(&w);cases++;good(&w,&o,threads,pause!=0);
            }
        }
    }
    struct witness w;struct ggml_pool_options o=options(&w);
    struct ggml_threadpool_params p=ggml_threadpool_params_default(4);p.poll=0;
    struct ggml_threadpool *t=NULL;size_t required;
    CHECK(ggml_pool_required_bytes(4,o.stack_bytes,&required)==0);
    o.max_reserved_bytes=required-1;CHECK(ggml_pool_create_checked(&p,&o,&t)==ENOMEM && !t);zero(&w);
    o.max_reserved_bytes=required;good(&w,&o,4,false);
    p.cpumask[4]=true;CHECK(!ggml_pool_affinity_supported());CHECK(ggml_pool_create_checked(&p,&o,&t)==ENOTSUP && !t);zero(&w);
    p.cpumask[4]=false;p.prio=GGML_SCHED_PRIO_HIGH;CHECK(ggml_pool_create_checked(&p,&o,&t)==ENOTSUP && !t);zero(&w);
    p.prio=GGML_SCHED_PRIO_NORMAL;
    p.strict_cpu=true;CHECK(ggml_pool_create_checked(&p,&o,&t)==ENOTSUP && !t);zero(&w);p.strict_cpu=false;
    /* Creation failure plus unconfirmed join retains all storage for retry. */
    w.site=THREAD_CREATE;w.ordinal=2;w.join_fail=true;
    CHECK(ggml_pool_create_checked(&p,&o,&t)==EBUSY && t);
    CHECK(atomic_load(&w.bytes)>0 && atomic_load(&w.handles)==1);
    w.join_fail=false;CHECK(ggml_pool_destroy_checked(&t)==0 && !t);zero(&w);
    good(&w,&o,4,false);
    CHECK(ggml_pool_required_bytes(4,SIZE_MAX,&required)==EOVERFLOW);
    /* Legacy entry remains usable for normal callers; invalid count rejects. */
    p.n_threads=0;CHECK(!ggml_threadpool_new(&p));p.n_threads=2;
    t=ggml_threadpool_new(&p);CHECK(t);graph(t,2,NULL);ggml_threadpool_free(t);
    graph(NULL,5,NULL); /* implicit pool exceeding default limit returns status */
    printf("cases=%u checks=%u failures=0 real_pthread=1 weights=0 affinity_supported=0\n",cases,checks);
    return 0;
}
