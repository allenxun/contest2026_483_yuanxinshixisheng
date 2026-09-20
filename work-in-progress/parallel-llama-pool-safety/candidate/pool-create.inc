static int pool_fault(const struct ggml_pool_hooks *h,enum ggml_pool_site s,unsigned n) {
    return h->fail ? h->fail(h->ctx,s,n) : 0;
}
static void pool_note(const struct ggml_pool_hooks *h,enum ggml_pool_resource r,int delta,size_t n) {
    if(h->note)h->note(h->ctx,r,delta,n);
}
struct ggml_pool_options ggml_pool_options_default(void) {
    struct ggml_pool_options o={0};o.max_reserved_bytes=4*1024*1024;
    o.stack_bytes=256*1024;o.max_threads=4;return o;
}
bool ggml_pool_affinity_supported(void) {return false;}
int ggml_pool_required_bytes(int n,size_t stack,size_t *out) {
    if(!out || n<1 || n>GGML_MAX_N_THREADS || !stack)return EINVAL;
    size_t workers=(size_t)n*sizeof(struct ggml_compute_state);
    if((size_t)(n-1) && stack>(SIZE_MAX-sizeof(struct ggml_threadpool)-workers)/(size_t)(n-1))return EOVERFLOW;
    *out=sizeof(struct ggml_threadpool)+workers+(size_t)(n-1)*stack;return 0;
}
int ggml_pool_create_checked(const struct ggml_threadpool_params *p,const struct ggml_pool_options *o,struct ggml_threadpool **out) {
    if(!out)return EINVAL;
    *out=NULL;
    if(!p || !o || p->n_threads<1 || p->n_threads>GGML_MAX_N_THREADS ||
       (unsigned)p->n_threads>o->max_threads)return EINVAL;
    if(p->prio!=GGML_SCHED_PRIO_NORMAL || p->strict_cpu || ggml_thread_cpumask_is_valid(p->cpumask))return ENOTSUP;
    size_t reserved=0;int rc=ggml_pool_required_bytes(p->n_threads,o->stack_bytes,&reserved);
    if(rc)return rc;
    if(reserved>o->max_reserved_bytes)return ENOMEM;
    if(pool_fault(&o->hooks,POOL_ALLOC,1))return ENOMEM;
    struct ggml_threadpool *t=ggml_aligned_malloc(sizeof(*t));
    if(!t)return ENOMEM;
    memset(t,0,sizeof(*t));t->safe_hooks=o->hooks;t->n_threads_max=p->n_threads;
    pool_note(&t->safe_hooks,POOL_BYTES,1,sizeof(*t));
    atomic_init(&t->n_graph,0);atomic_init(&t->n_barrier,0);atomic_init(&t->n_barrier_passed,0);
    atomic_init(&t->current_chunk,0);atomic_init(&t->stop,false);atomic_init(&t->pause,p->paused);
    atomic_init(&t->abort,-1);atomic_init(&t->n_threads_cur,p->n_threads);
    t->poll=p->poll;t->prio=p->prio;t->ec=GGML_STATUS_SUCCESS;
    size_t bytes=sizeof(struct ggml_compute_state)*(size_t)p->n_threads;
    if(pool_fault(&t->safe_hooks,WORKERS_ALLOC,1)){rc=ENOMEM;goto fail;}
    t->workers=ggml_aligned_malloc(bytes);
    if(!t->workers){rc=ENOMEM;goto fail;}
    pool_note(&t->safe_hooks,POOL_BYTES,1,bytes);memset(t->workers,0,bytes);
    for(int j=0;j<p->n_threads;j++){t->workers[j].threadpool=t;t->workers[j].ith=j;}
    rc=pool_fault(&t->safe_hooks,MUTEX_INIT,1)?EAGAIN:pthread_mutex_init(&t->mutex,NULL);
    if(rc)goto fail;
    t->safe_mutex=true;pool_note(&t->safe_hooks,POOL_MUTEX,1,0);
    rc=pool_fault(&t->safe_hooks,COND_INIT,1)?EAGAIN:pthread_cond_init(&t->cond,NULL);
    if(rc)goto fail;
    t->safe_cond=true;pool_note(&t->safe_hooks,POOL_COND,1,0);
    rc=pool_fault(&t->safe_hooks,ATTR_INIT,1)?EAGAIN:pthread_attr_init(&t->safe_attr);
    if(rc)goto fail;
    t->safe_attr_ready=true;pool_note(&t->safe_hooks,POOL_ATTR,1,0);
    rc=pool_fault(&t->safe_hooks,ATTR_STACK,1)?EINVAL:pthread_attr_setstacksize(&t->safe_attr,o->stack_bytes);
    if(!rc)for(int j=1;j<p->n_threads;j++) {
        rc=pool_fault(&t->safe_hooks,THREAD_CREATE,(unsigned)j)?EAGAIN:
            pthread_create(&t->workers[j].thrd,&t->safe_attr,ggml_graph_compute_secondary_thread,&t->workers[j]);
        if(rc)break;
        t->safe_created++;pool_note(&t->safe_hooks,POOL_THREAD,1,0);
    }
    if(rc)goto fail;
    *out=t;return 0;
fail:
    *out=t;
    {
        int cleanup=ggml_pool_destroy_checked(out);
        return cleanup?cleanup:rc;
    }
}
static struct ggml_threadpool *ggml_threadpool_new_impl(struct ggml_threadpool_params *p,struct ggml_cgraph *g,struct ggml_cplan *plan) {
    struct ggml_threadpool *t=NULL;struct ggml_pool_options o=ggml_pool_options_default();
    int rc=ggml_pool_create_checked(p,&o,&t);
    if(rc) {
        /* Legacy pointer-only API cannot transfer quarantine on join failure.
           Allocation/create failures with successful cleanup return NULL. */
        if(t)GGML_ABORT("pool cleanup failed; use checked API for quarantine");
        errno=rc;return NULL;
    }
    t->cgraph=g;t->cplan=plan;return t;
}
