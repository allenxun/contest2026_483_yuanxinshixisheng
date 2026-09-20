#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
struct control {uintptr_t size,align;union{uintptr_t offset;void*ptr;}loc;void*initial;};
extern void *__emutls_get_address(void*);
extern int __cxa_thread_atexit(void(*)(void*),void*,void*);
struct group {uintptr_t value;};
static _Thread_local struct group *current;
static void (*destroy_group)(void*);
int task_tls_alloc(void(*d)(void*)){destroy_group=d;return 0;}
uintptr_t task_tls_get_value(int i){assert(i==0&&current);return current->value;}
int task_tls_set_value(int i,uintptr_t v){assert(i==0&&current);current->value=v;return 0;}
static int initial=17;
static struct control value_control={sizeof(int),64,{0},&initial};
static struct control zero_control={32,128,{0},NULL};
static atomic_uint destructors;
struct args {struct group*g;pthread_barrier_t*barrier;int number;};
static void first(void*p){int*v=__emutls_get_address(&value_control);assert(*v==*(int*)p+1000);atomic_fetch_add(&destructors,1);free(p);}
static void second(void*p){int*v=__emutls_get_address(&value_control);assert(*v==*(int*)p);*v+=1000;atomic_fetch_add(&destructors,1);}
static void *worker(void*ptr){
 struct args*a=ptr;current=a->g;int*v=__emutls_get_address(&value_control);
 assert(*v==17&&((uintptr_t)v%64)==0);*v=a->number;
 unsigned char*z=__emutls_get_address(&zero_control);assert((uintptr_t)z%128==0);
 for(unsigned i=0;i<32;i++)assert(z[i]==0);
 pthread_barrier_wait(a->barrier);assert(*v==a->number);
 assert(__emutls_get_address(&value_control)==v);
 int*saved=malloc(sizeof(int));assert(saved);*saved=a->number;
 assert(!__cxa_thread_atexit(first,saved,NULL));assert(!__cxa_thread_atexit(second,saved,NULL));
 return NULL;
}
int main(void){
 for(unsigned round=0;round<16;round++){
  struct group groups[2]={{0},{0}};pthread_t threads[4];struct args a[4];pthread_barrier_t barrier;
  assert(!pthread_barrier_init(&barrier,NULL,4));
  for(unsigned i=0;i<4;i++){a[i]=(struct args){&groups[i/2],&barrier,(int)(100*round+i)};assert(!pthread_create(&threads[i],NULL,worker,&a[i]));}
  for(unsigned i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
  for(unsigned i=0;i<2;i++){assert(groups[i].value);current=&groups[i];destroy_group((void*)groups[i].value);groups[i].value=0;}
  pthread_barrier_destroy(&barrier);
 }
 assert(atomic_load(&destructors)==128);assert(value_control.loc.ptr==NULL);
 pid_t child=fork();assert(child>=0);
 if(!child){struct group g={0};current=&g;struct control bad={4,24,{0},NULL};__emutls_get_address(&bad);_exit(1);}
 int status;assert(waitpid(child,&status,0)==child);assert(WIFSIGNALED(status)&&WTERMSIG(status)==SIGABRT);
 puts("PASS: 64 threads / 32 groups, isolation, templates, alignment, 128 LIFO destructors, TLS access during cleanup, invalid alignment rejected");
}
