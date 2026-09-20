#define MR_TESTING
#include "input/formal/model_reader.c"
#define MI_TESTING
#include "model_integrity.c"
#include <stdlib.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static const char *fixture;
static int scenario,events,early_ready,event_error;
static void change_file(int truncate, uint64_t offset) {
    FILE *f=fopen(fixture,truncate?"wb":"r+b");
    if(!f){event_error=1;return;}
    if(!truncate && _fseeki64(f,(int64_t)offset,SEEK_SET)!=0) event_error=1;
    if(fputc('X',f)==EOF || fclose(f)!=0) event_error=1;
}
void mi_test_event(int event,mi_model *m) {
    if(mi_is_ready(m)) early_ready=1;
    if(event==1 && ++events==1) {
        if(scenario==2 || scenario==12) fault.read_error=1;
        if(scenario==3) change_file(1,0);
        if(scenario==4) change_file(0,m->file.position);
        if(scenario==6) fault.stat_error=1;
        if(scenario==12) fault.close_error=1;
    }
    if(event==2 && scenario==5) fault.seek_error=1;
}
static int unhex(const char *s,unsigned char out[32]) {
    size_t i; if(strlen(s)!=64)return 0;
    for(i=0;i<32;++i){unsigned v; if(sscanf(s+i*2,"%2x",&v)!=1)return 0;out[i]=(unsigned char)v;}
    return 1;
}
int main(int argc,char **argv) {
    mi_model model=MI_MODEL_INIT; mr_file file=MR_FILE_INIT;
    unsigned char expected[32],actual[32],scratch[4096],byte;
    uint64_t length,initial; size_t capacity; int rc,fd;
    CHECK(argc==8); fixture=argv[1]; length=strtoull(argv[2],NULL,10);
    CHECK(unhex(argv[3],expected)); capacity=(size_t)strtoul(argv[4],NULL,10);
    scenario=atoi(argv[5]); initial=strtoull(argv[6],NULL,10);
    CHECK(!mi_is_ready(&model));
    /* Independent published empty-message SHA-256 vector; file API still rejects empty models. */
    {sha256_t sha; unsigned char empty[32];
      CHECK(unhex("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",empty));
      sha256_init(&sha);sha256_update(&sha,(const unsigned char*)"",0);sha256_final(&sha,actual);
      CHECK(memcmp(empty,actual,32)==0);}
    if(scenario==14) {
        CHECK(mr_open(&file,fixture,0,1,4096)==EINVAL && file.fd==-1);
        CHECK(mi_verify_open(&model,&file,0,expected,scratch,1)!=0 && !mi_is_ready(&model));
        puts("PASS empty SHA vector; empty model rejected");return 0;
    }
    CHECK(mi_read(&model,&byte,1)==EACCES && !mi_is_ready(&model));
    CHECK(mr_open(&file,fixture,length,length,4096)==0);
    CHECK(mr_seek(&file,initial)==0); fd=file.fd;
    if(scenario==1)expected[0]^=1;
    if(scenario==7)fault.seek_error=1;
    rc=mi_verify_open(&model,&file,scenario==10?length-1:(scenario==11?UINT64_MAX:length),expected,
                      scenario==8?NULL:scratch,scenario==9?0:capacity);
    CHECK(file.fd==-1 && !early_ready && !event_error);
    if(scenario>=1 && scenario<=12) {
        CHECK(rc!=0 && model.state==MI_FAILED && !mi_is_ready(&model));
        CHECK(model.file.fd==-1 && fault.closes==1);
        if(scenario==12)CHECK(model.file.close_error==EIO);
        CHECK(mi_read(&model,&byte,1)==EACCES && fault.closes==1);
        CHECK(!mi_is_ready(&model));
        printf("PASS failure %d revoked READY and closed exactly once\n",scenario);return 0;
    }
    CHECK(rc==0 && mi_is_ready(&model) && model.file.fd==fd && model.file.position==initial);
    CHECK(fault.closes==0);
    if(scenario==16) {
        mr_file second=MR_FILE_INIT; CHECK(mr_open(&second,fixture,length,length,4096)==0);
        CHECK(mi_verify_open(&model,&second,length,expected,scratch,4096)==EBUSY);
        CHECK(second.fd==-1 && !mi_is_ready(&model) && model.file.fd==-1 && fault.closes==2);
        puts("PASS reverify occupied gate revokes prior READY and closes both handles");return 0;
    }
    if(scenario==17) {
        fault.read_error=1;CHECK(mi_read(&model,&byte,1)==EIO);
        CHECK(!mi_is_ready(&model) && model.file.fd==-1 && fault.closes==1);
        puts("PASS later read failure revokes READY and releases handle");return 0;
    }
    if(scenario==13) {
        CHECK(mi_seek(&model,UINT64_MAX)!=0 && !mi_is_ready(&model) && fault.closes==1);
        puts("PASS verified read state revoked on later seek error");return 0;
    }
    if(scenario==15) {
        change_file(0,0);CHECK(!event_error);
        CHECK(mi_seek(&model,0)==0 && mi_read(&model,&byte,1)==0 && byte=='X');
        puts("LIMITATION observed: same-length mutation AFTER verification readable; immutable storage required");
    }
    CHECK(mi_close(&model)==0 && !mi_is_ready(&model) && fault.closes==1);
    CHECK(mi_close(&model)==0 && fault.closes==1);
    printf("PASS scenario %d length %llu chunk %zu initial position %llu same handle restored\n",scenario,(unsigned long long)length,capacity,(unsigned long long)initial);
    (void)argv[7];return 0;
}

