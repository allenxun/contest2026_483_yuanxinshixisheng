#define MR_TESTING
#include "model_reader.c"
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static void reset(void){ memset(&fault,0,sizeof(fault)); }
int main(int argc,char **argv) {
    mr_file f=MR_FILE_INIT; char b[32]={0}; int i; FILE *w;
    CHECK(argc>=2);
    CHECK(mr_open(&f,argv[1],0,16,16)==EINVAL && f.fd==-1);
    CHECK(mr_open(&f,argv[1],UINT64_MAX,UINT64_MAX,16)==EINVAL && f.fd==-1);
    CHECK(mr_open(&f,argv[1],16,15,16)==EINVAL && f.fd==-1);
    CHECK(mr_open(&f,argv[1],16,16,16)==0);
    CHECK(mr_read_exact(&f,b,16)==0 && !memcmp(b,"0123456789abcdef",16));
    CHECK(mr_seek(&f,16)==0 && mr_read_exact(&f,NULL,0)==0);
    CHECK(mr_close(&f)==0 && mr_close(&f)==0); puts("PASS real small file, EOF zero read, idempotent close");
    reset(); CHECK(mr_open(&f,argv[1],15,16,16)!=0 && f.fd==-1 && fault.closes==1); puts("PASS exact length mismatch closes");
    reset(); CHECK(mr_open(&f,argv[1],16,16,16)==0);
    CHECK(mr_open(&f,argv[1],16,16,16)==EBUSY && f.fd==-1 && fault.closes==1);
    reset(); CHECK(mr_open(&f,argv[1],16,16,16)==0); CHECK(mr_seek(&f,15)==0);
    CHECK(mr_read_exact(&f,b,2)!=0 && f.fd==-1);
    puts("PASS open budgets, reopen ownership, cross-EOF range");
    for(i=0;i<7;++i) {
        reset(); CHECK(mr_open(&f,argv[1],16,16,16)==0);
        if(i==0) CHECK(mr_seek(&f,UINT64_MAX)!=0);
        if(i==1) CHECK(mr_read_exact(&f,b,17)!=0);
        if(i==2) {fault.eof=1; CHECK(mr_read_exact(&f,b,8)!=0);}
        if(i==3) {fault.read_error=1; CHECK(mr_read_exact(&f,b,8)!=0);}
        if(i==4) {fault.stat_error=1; CHECK(mr_read_exact(&f,b,8)!=0);}
        if(i==5) {fault.seek_error=1; CHECK(mr_seek(&f,1)!=0);}
        if(i==6) {fault.eintr=17; CHECK(mr_read_exact(&f,b,8)==EINTR);}
        CHECK(f.fd==-1 && fault.closes==1); CHECK(mr_close(&f)==0 && fault.closes==1);
    }
    puts("PASS overflow/budget; injected EOF/read/stat/seek/EINTR exhaustion closes once");
    reset(); CHECK(mr_open(&f,argv[1],16,16,16)==0); fault.eintr=2; fault.short_read=1;
    CHECK(mr_read_exact(&f,b,16)==0 && !memcmp(b,"0123456789abcdef",16));
    fault.close_error=1; CHECK(mr_close(&f)==EIO && f.close_error==EIO && f.fd==-1);
    puts("PASS injected EINTR+short read recovery, close error reported after real release");
    reset(); CHECK(mr_open(&f,argv[1],16,16,16)==0);
    w=fopen(argv[1],"wb"); CHECK(w!=NULL); CHECK(fwrite("x",1,1,w)==1); CHECK(fclose(w)==0);
    CHECK(mr_read_exact(&f,b,1)!=0 && f.fd==-1); puts("PASS real concurrent file truncation detected");
    CHECK(mr_open(&f,"/dev/blocked-not-opened",1,16,16)!=0 && f.fd==-1);
#ifdef _WIN32
    CHECK(mr_open(&f,"C:\\NUL",1,16,16)!=0);
    CHECK(mr_open(&f,"\\\\.\\PhysicalDrive0",1,16,16)!=0);
    CHECK(mr_open(&f,"C:\\x:stream",1,16,16)!=0);
    CHECK(mr_open(&f,"C:\\a\\..\\x",1,16,16)!=0);
#endif
    puts("PASS lexical prohibited-path rejection (no device opened)");
    if(argc==3) {
        uint64_t edge=UINT64_C(2147483648)+123;
        reset(); CHECK(mr_open(&f,argv[2],edge+4,edge+4,16)==0);
        CHECK(mr_seek(&f,edge)==0 && mr_read_exact(&f,b,4)==0 && !memcmp(b,"EDGE",4));
        CHECK(mr_seek(&f,edge-4)==0 && mr_read_exact(&f,b,4)==0);
        CHECK(b[0]==0&&b[1]==0&&b[2]==0&&b[3]==0); CHECK(mr_close(&f)==0);
        puts("PASS real >2GiB sparse seek/read and zero hole");
    }
    puts("PASS all C checks"); return 0;
}

