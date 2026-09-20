int ggml_pool_destroy_checked(struct ggml_threadpool **out) {
    if(!out)return EINVAL;
    struct ggml_threadpool *t=*out;if(!t)return 0;
    if(t->safe_joined<t->safe_created) {
        int rc=pthread_mutex_lock(&t->mutex);if(rc)return rc;
        t->stop=true;t->pause=false;
        int wake=pthread_cond_broadcast(&t->cond);
        int unlock=pthread_mutex_unlock(&t->mutex);
        if(wake || unlock)return wake?wake:unlock;
        while(t->safe_joined<t->safe_created) {
            unsigned j=t->safe_joined+1;
            int ret=pool_fault(&t->safe_hooks,THREAD_JOIN,j)?EBUSY:pthread_join(t->workers[j].thrd,NULL);
            if(ret)return ret; /* retain buffer, flags and remaining handles */
            t->safe_joined++;pool_note(&t->safe_hooks,POOL_THREAD,-1,0);
        }
    }
    if(t->safe_attr_ready){int rc=pthread_attr_destroy(&t->safe_attr);if(rc)return rc;t->safe_attr_ready=false;pool_note(&t->safe_hooks,POOL_ATTR,-1,0);}
    if(t->safe_cond){int rc=pthread_cond_destroy(&t->cond);if(rc)return rc;t->safe_cond=false;pool_note(&t->safe_hooks,POOL_COND,-1,0);}
    if(t->safe_mutex){int rc=pthread_mutex_destroy(&t->mutex);if(rc)return rc;t->safe_mutex=false;pool_note(&t->safe_hooks,POOL_MUTEX,-1,0);}
    if(t->workers){size_t bytes=sizeof(struct ggml_compute_state)*(size_t)t->n_threads_max;
        ggml_aligned_free(t->workers,bytes);pool_note(&t->safe_hooks,POOL_BYTES,-1,bytes);}
    struct ggml_pool_hooks h=t->safe_hooks;
    ggml_aligned_free(t,sizeof(*t));pool_note(&h,POOL_BYTES,-1,sizeof(*t));*out=NULL;return 0;
}
void ggml_threadpool_free(struct ggml_threadpool *t) {
    int rc=ggml_pool_destroy_checked(&t);
    if(rc)GGML_ABORT("pool destroy failed; use checked API to retain ownership");
}
