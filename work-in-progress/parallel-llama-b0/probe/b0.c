#include "llama.h"
#include "ggml-cpu.h"
#include "ggml-alloc.h"
#include "ggml-backend.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

/* No weights, no network. This is a C translation unit linked to real C++ libs. */
static int compute(int n_threads) {
    int rc=1;
    ggml_backend_t backend=NULL;
    ggml_threadpool_t pool=NULL;
    struct ggml_context *ctx=NULL;
    ggml_backend_buffer_t buffer=NULL;
    struct ggml_threadpool_params tp=ggml_threadpool_params_default(n_threads);
    struct ggml_init_params ip={1024*1024,NULL,true};
    backend=ggml_backend_cpu_init();
    if(!backend) goto done;
    pool=ggml_threadpool_new(&tp);
    if(!pool) goto done;
    ggml_backend_cpu_set_n_threads(backend,n_threads);
    ggml_backend_cpu_set_threadpool(backend,pool);
    ctx=ggml_init(ip);
    if(!ctx) goto done;
    struct ggml_tensor *x=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,4096);
    struct ggml_tensor *y=ggml_sqr(ctx,x);
    struct ggml_tensor *z=ggml_sum(ctx,y);
    struct ggml_cgraph *graph=ggml_new_graph(ctx);
    ggml_build_forward_expand(graph,z);
    buffer=ggml_backend_alloc_ctx_tensors(ctx,backend);
    if(!buffer) goto done;
    float input[4096],result=0;
    for(int i=0;i<4096;i++)input[i]=2.0f;
    ggml_backend_tensor_set(x,input,0,sizeof(input));
    if(ggml_backend_graph_compute(backend,graph)!=GGML_STATUS_SUCCESS) goto done;
    ggml_backend_tensor_get(z,&result,0,sizeof(result));
    if(fabsf(result-16384.0f)>0.01f) goto done;
    printf("cpu_graph threads=%d result=%.0f expected=16384\n",n_threads,(double)result);
    rc=0;
done:
    if(buffer) ggml_backend_buffer_free(buffer);
    if(ctx) ggml_free(ctx);
    if(backend) ggml_backend_free(backend);
    if(pool) ggml_threadpool_free(pool);
    return rc;
}
int main(int argc,char **argv) {
    if(argc!=3){fputs("usage: b0-probe missing-path invalid-gguf-path\n",stderr);return 2;}
    int failed=0;
    llama_backend_init();
    if(ggml_backend_reg_count()!=1 || ggml_backend_reg_by_name("CPU")==NULL)failed++;
    if(ggml_backend_load("disabled-backend")!=NULL)failed++;
    ggml_backend_load_all_from_path("disabled-directory");
    if(ggml_backend_reg_count()!=1)failed++;
    for(int i=0;i<4;i++) failed+=compute(i%2?4:2);
    struct llama_model_params mp=llama_model_default_params();
    mp.n_gpu_layers=0;mp.use_mmap=false;mp.use_mlock=false;
    for(int i=1;i<=2;i++) {
        struct llama_model *model=llama_model_load_from_file(argv[i],mp);
        if(model){failed++;llama_model_free(model);}
        printf("negative_load case=%d rejected=%d\n",i,model==NULL);
    }
    llama_backend_free();
    printf("failures=%d weights_loaded=0 inference_performed=0 host_only=1\n",failed);
    return failed?1:0;
}
