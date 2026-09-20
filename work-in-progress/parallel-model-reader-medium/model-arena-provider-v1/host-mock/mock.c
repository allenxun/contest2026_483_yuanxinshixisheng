#include <nuttx/mm/k7_model_arena.h>
#include "mock.h"
#include <errno.h>
#include <stdlib.h>
static _Alignas(64) unsigned char memory[1048576];
static int mode,ready;static size_t occupied;static unsigned gets,puts;
void kap_mock_mode(int m){mode=m;}
uintptr_t kap_mock_base(void){return (uintptr_t)memory;}
unsigned kap_mock_alloc_calls(void){return gets;}
unsigned kap_mock_free_calls(void){return puts;}
int k7_model_arena_initialize(void){if(mode==1)return -ENOMEM;ready=1;return 0;}
void *k7_model_alloc(size_t n){
    ++gets;if(!ready || !n || n>sizeof(memory) || occupied || mode==2)return NULL;
    occupied=n;if(mode==3)return memory+1;if(mode==4)return memory+sizeof(memory);return memory;
}
void k7_model_free(void *p){
    ++puts;if(p!=memory || !occupied)abort();
    if(mode!=5)occupied=0;
}
size_t k7_model_available(void){return ready?sizeof(memory)-occupied:0;}
