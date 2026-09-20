#include "model_integrity.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
    mr_file file=MR_FILE_INIT; mi_model model=MI_MODEL_INIT;
    unsigned char digest[32],scratch[64],out[3];unsigned i,v;int e;
    if(argc!=3 || strlen(argv[2])!=64)return 2;
    for(i=0;i<32;++i){if(sscanf(argv[2]+i*2,"%2x",&v)!=1)return 2;digest[i]=(unsigned char)v;}
    e=mr_open(&file,argv[1],3,3,64);if(e)return 3;
    e=mi_verify_open(&model,&file,3,digest,scratch,sizeof(scratch));
    if(e || !mi_is_ready(&model) || file.fd!=-1 || mi_read(&model,out,3) || memcmp(out,"abc",3)) {mi_close(&model);return 4;}
    if(mi_close(&model) || mi_is_ready(&model))return 5;
    puts("PASS production objects linked and executed, verified abc through gate");return 0;
}
