from pathlib import Path
import difflib
R=Path(__file__).resolve().parents[1]
original=(R/'vendor/llama.cpp-74d4f5b041ad837153b0e90fc864b8290e01d8d5/ggml/src/ggml-cpu/ggml-cpu.c').read_text(encoding='utf8')
s=original
s='#include "ggml-pool-safe.h"\n#if defined(GGML_USE_OPENMP)\n#error "pool safety candidate requires POSIX pool, no OpenMP"\n#endif\n'+s
# Only the Win32 thread emulation and pool synchronization definitions are
# changed; architecture and other Windows functionality retain true platform.
needle='#if defined(_WIN32)\n\n#define WIN32_LEAN_AND_MEAN'
assert s.count(needle)==1;s=s.replace(needle,'#if defined(_WIN32) && !defined(GGML_POOL_POSIX)\n\n#define WIN32_LEAN_AND_MEAN')
needle='#if defined(_WIN32)\n\ntypedef CONDITION_VARIABLE'
assert s.count(needle)==1;s=s.replace(needle,'#if defined(_WIN32) && !defined(GGML_POOL_POSIX)\n\ntypedef CONDITION_VARIABLE')
s=s.replace('struct ggml_threadpool {','''struct ggml_threadpool {
    struct ggml_pool_hooks safe_hooks;
    unsigned safe_created, safe_joined;
    bool safe_mutex, safe_cond, safe_attr_ready;
    pthread_attr_t safe_attr;''',1)
start=s.index('void ggml_threadpool_free(');end=s.index('\n#ifndef GGML_USE_OPENMP',s.index('\n}',start)+2)
s=s[:start]+'''static int pool_fault(const struct ggml_pool_hooks *,enum ggml_pool_site,unsigned);
static void pool_note(const struct ggml_pool_hooks *,enum ggml_pool_resource,int,size_t);
'''+(R/'candidate/pool-destroy.inc').read_text(encoding='utf8')+s[end:]
start=s.index('static struct ggml_threadpool * ggml_threadpool_new_impl(')
end=s.index('\nstruct ggml_threadpool * ggml_threadpool_new(',start)
s=s[:start]+(R/'candidate/pool-create.inc').read_text(encoding='utf8')+s[end:]
s=s.replace('threadpool = ggml_threadpool_new_impl(&ttp, cgraph, cplan);','threadpool = ggml_threadpool_new_impl(&ttp, cgraph, cplan);\n        if (!threadpool) return GGML_STATUS_ALLOC_FAILED;')
start=s.index('static thread_ret_t ggml_graph_compute_secondary_thread(void* data) {')
tail=s[start:]
tail=tail.replace('    ggml_thread_apply_priority(threadpool->prio);','    pool_note(&threadpool->safe_hooks,POOL_RUNNING,1,(size_t)state->ith);\n    ggml_thread_apply_priority(threadpool->prio);',1)
tail=tail.replace('            ggml_graph_compute_thread(state);','            pool_note(&threadpool->safe_hooks,POOL_COMPUTE,1,(size_t)state->ith);\n            ggml_graph_compute_thread(state);',1)
tail=tail.replace('    return (thread_ret_t) 0;','    pool_note(&threadpool->safe_hooks,POOL_RUNNING,-1,(size_t)state->ith);\n    return (thread_ret_t) 0;',1)
s=s[:start]+tail
(R/'candidate/ggml-cpu.c').write_text(s,encoding='utf8',newline='\n')
(R/'candidate/pool-safety.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='a/ggml/src/ggml-cpu/ggml-cpu.c',tofile='b/ggml/src/ggml-cpu/ggml-cpu.c')),encoding='utf8',newline='\n')
print('derived_real_cpu_source')
