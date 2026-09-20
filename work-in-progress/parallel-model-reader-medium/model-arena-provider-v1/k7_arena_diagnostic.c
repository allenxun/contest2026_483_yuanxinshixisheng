#include "k7_arena_diagnostic.h"
#include "ggml-alloc.h"
#include <nuttx/mm/k7_model_arena.h>
#include <errno.h>
#include <limits.h>
#include <string.h>
/* Single diagnostic owner only; metadata BSS is not placed on NuttX task stack. */
static _Alignas(64) unsigned char metadata[32768];
int kap_diagnostic(struct kap_state *s,struct kap_report *r) {
    ggml_backend_buffer_type_t type=NULL;ggml_backend_buffer_t buffer=NULL;
    struct ggml_context *ctx=NULL;struct ggml_tensor *t[2]={NULL,NULL};
    struct k7_buft_config config;int rc=0;float input[64],output[64];
    if(!s || !r)return EINVAL;
    memset(r,0,sizeof(*r));
    r->initialize_status=kap_initialize(s);
    if(r->initialize_status) {r->operation_error=EIO;return EIO;}
    r->available_before=k7_model_available();
    config=(struct k7_buft_config){kap_provider(s),64,KAP_LIMIT,KAP_LIMIT};
    rc=k7_buft_create(&config,&s->retained_type);type=s->retained_type;if(rc)goto done;
    /* Upstream context small metadata malloc can abort; not fixed by this adapter. */
    ctx=ggml_init((struct ggml_init_params){sizeof(metadata),metadata,true});
    if(!ctx){rc=ENOMEM;goto done;}
    for(unsigned i=0;i<2;++i){t[i]=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,64,64);if(!t[i]){rc=ENOMEM;goto done;}}
    buffer=ggml_backend_alloc_ctx_tensors_from_buft(ctx,type);
    if(!buffer){rc=ENOMEM;goto done;}
    r->addresses_valid=1;
    for(unsigned i=0;i<2;++i) {
        if(!kap_range_valid(t[i]->data,ggml_nbytes(t[i]))){r->addresses_valid=0;rc=EFAULT;goto done;}
        for(unsigned row=0;row<64;++row) {
            for(unsigned x=0;x<64;++x)input[x]=(float)((int)(row*64+x)-2048+(int)i);
            ggml_backend_tensor_set(t[i],input,row*sizeof(input),sizeof(input));
            ggml_backend_tensor_get(t[i],output,row*sizeof(output),sizeof(output));
            for(unsigned x=0;x<64;++x){++r->values_checked;if(input[x]!=output[x])++r->mismatches;}
        }
    }
    if(r->mismatches)rc=EILSEQ;
done:
    if(buffer)ggml_backend_buffer_free(buffer);
    if(ctx)ggml_free(ctx); /* Discard even after allocation failure; no stale tensor reuse. */
    if(type){int destroy=k7_buft_destroy(&s->retained_type);if(destroy)rc=destroy;}
    r->available_after=k7_model_available();
    r->peak_bytes=s->peak_bytes;r->allocations=s->allocations;r->releases=s->releases;
    r->live_slots=kap_live_slots(s);r->errors=s->errors;r->quarantined=s->quarantined;
    r->returned_to_baseline=r->available_after==r->available_before && !r->live_slots && !s->live_bytes;
    if(!r->returned_to_baseline){++s->errors;r->errors=s->errors;}
    if(!r->returned_to_baseline || r->errors || r->quarantined)rc=EIO;
    r->operation_error=rc;return rc;
}

