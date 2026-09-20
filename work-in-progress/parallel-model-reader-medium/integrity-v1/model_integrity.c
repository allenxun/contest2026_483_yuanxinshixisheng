#include "model_integrity.h"
#include "sha256_namespace.h"
#include <errno.h>
#include <string.h>
#ifdef MI_TESTING
/* Test-only deterministic event injection, absent from production build. */
extern void mi_test_event(int event, mi_model *model);
#define MI_EVENT(x) mi_test_event((x),m)
#else
#define MI_EVENT(x) ((void)0)
#endif
static int mi_failure(mi_model *m,int error) {
    if(m) {
        if(m->file.fd>=0) mr_close(&m->file);
        m->state=MI_FAILED;
    }
    return error;
}
int mi_is_ready(const mi_model *m) { return m && m->state==MI_READY && m->file.fd>=0; }
int mi_close(mi_model *m) {
    int e=0;
    if(!m) return EINVAL;
    m->state=MI_CLOSED;
    if(m->file.fd>=0) e=mr_close(&m->file);
    else e=m->file.close_error;
    return e;
}
int mi_verify_open(mi_model *m,mr_file *opened,uint64_t length,
                   const unsigned char expected[32],void *scratch,size_t capacity) {
    sha256_t sha; unsigned char actual[32]; unsigned difference=0;
    uint64_t original,remaining; size_t i; int e;
    if(!m) { if(opened && opened->fd>=0) mr_close(opened); return EINVAL; }
    /* An alias is invalid, but must revoke any earlier READY state. */
    if(opened==&m->file) return mi_failure(m,EINVAL);
    if(m->file.fd>=0) {
        if(opened && opened->fd>=0) mr_close(opened);
        return mi_failure(m,EBUSY);
    }
    m->state=MI_UNVERIFIED;
    if(!opened) return mi_failure(m,EINVAL);
    m->file=*opened;
    { const mr_file empty=MR_FILE_INIT; *opened=empty; }
    if(m->file.fd<0) return mi_failure(m,EBADF);
    /* SHA-256 encodes bit count in 64 bits. Reject byte counts that overflow it. */
    if(!length || length>UINT64_MAX/8 || length!=m->file.length || !expected ||
       !scratch || !capacity || capacity>MI_SCRATCH_MAX || capacity>m->file.max_read ||
       m->file.position>length) return mi_failure(m,EINVAL);
    original=m->file.position;
    m->state=MI_VERIFYING;
    e=mr_seek(&m->file,0); if(e) return mi_failure(m,e);
    sha256_init(&sha); remaining=length;
    while(remaining) {
        size_t amount=remaining>capacity?capacity:(size_t)remaining;
        e=mr_read_exact(&m->file,scratch,amount); if(e) return mi_failure(m,e);
        sha256_update(&sha,(const unsigned char*)scratch,amount);
        remaining-=amount;
        MI_EVENT(1);
    }
    sha256_final(&sha,actual);
    for(i=0;i<sizeof(actual);++i) difference|=(unsigned)(actual[i]^expected[i]);
    if(difference) return mi_failure(m,EILSEQ);
    MI_EVENT(2);
    /* Includes reader fstat length check. Only successful restoration commits READY. */
    e=mr_seek(&m->file,original); if(e) return mi_failure(m,e);
    m->state=MI_READY;
    return 0;
}
int mi_read(mi_model *m,void *dst,size_t length) {
    int e;
    if(!mi_is_ready(m)) return mi_failure(m,EACCES);
    e=mr_read_exact(&m->file,dst,length); return e?mi_failure(m,e):0;
}
int mi_seek(mi_model *m,uint64_t offset) {
    int e;
    if(!mi_is_ready(m)) return mi_failure(m,EACCES);
    e=mr_seek(&m->file,offset); return e?mi_failure(m,e):0;
}
