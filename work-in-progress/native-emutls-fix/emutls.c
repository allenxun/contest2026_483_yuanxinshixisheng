/* Task-group-aware emulated TLS for the pinned single-thread GCC runtime.
 * C only: this allocator must not itself depend on compiler TLS. */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#ifndef K7_TLS_HOST_TEST
#include <nuttx/config.h>
#include <nuttx/tls_task.h>
#else
extern int task_tls_alloc(void (*)(void *));
extern uintptr_t task_tls_get_value(int);
extern int task_tls_set_value(int, uintptr_t);
#endif

struct control { uintptr_t size, align; union {uintptr_t offset;void *ptr;} loc; void *initial; };
struct block { struct block *next;struct control *control;void *bytes; };
struct dtor {struct dtor *next;void (*function)(void *);void *object;};
struct context {pthread_key_t key;struct block *blocks;struct dtor *dtors;unsigned count,dtor_count;};
struct k7_tls_group {pthread_key_t key;};
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static int group_slot=-1;
static void thread_destroy(void *);
static void group_destroy(void *value)
{
 struct k7_tls_group *g=value;
 /* NuttX exit destroys thread TLS before task-group TLS. */
 if(pthread_key_delete(g->key))abort();
 free(g);
}
static struct context *get_context(void)
{
 struct k7_tls_group *g;struct context *c;
 if(pthread_mutex_lock(&gate))abort();
 if(group_slot<0){group_slot=task_tls_alloc(group_destroy);if(group_slot<0)abort();}
 g=(struct k7_tls_group *)task_tls_get_value(group_slot);
 if(!g){
  g=calloc(1,sizeof(*g));if(!g)abort();
  if(pthread_key_create(&g->key,thread_destroy)){free(g);abort();}
  if(task_tls_set_value(group_slot,(uintptr_t)g)){pthread_key_delete(g->key);free(g);abort();}
 }
 pthread_key_t key=g->key;
 if(pthread_mutex_unlock(&gate))abort();
 c=pthread_getspecific(key);
 if(!c){c=calloc(1,sizeof(*c));if(!c)abort();c->key=key;if(pthread_setspecific(key,c)){free(c);abort();}}
 return c;
}
static void thread_destroy(void *value)
{
 struct context *c=value;
 /* POSIX may clear the key before its callback. Destructors may access TLS. */
 if(pthread_setspecific(c->key,c))abort();
 unsigned calls=0;
 while(c->dtors){
  if(++calls>512)abort();
  struct dtor *d=c->dtors;c->dtors=d->next;--c->dtor_count;
  d->function(d->object);free(d);
 }
 while(c->blocks){struct block *b=c->blocks;c->blocks=b->next;free(b->bytes);free(b);}
 if(pthread_setspecific(c->key,NULL))abort();
 free(c);
}
void *__emutls_get_address(void *raw_control)
{
 struct control *control=raw_control;
 if(!control||!control->size||control->size>16u*1024u*1024u)abort();
 struct context *c=get_context();
 for(struct block *b=c->blocks;b;b=b->next)if(b->control==control)return b->bytes;
 size_t alignment=control->align;if(alignment<sizeof(void*))alignment=sizeof(void*);
 if((alignment&(alignment-1))||alignment>1024u*1024u||c->count>=256)abort();
 struct block *b=calloc(1,sizeof(*b));if(!b)abort();
 if(posix_memalign(&b->bytes,alignment,control->size)){free(b);abort();}
 if(control->initial)memcpy(b->bytes,control->initial,control->size);else memset(b->bytes,0,control->size);
 b->control=control;b->next=c->blocks;c->blocks=b;++c->count;
 return b->bytes;
}
int __cxa_thread_atexit_impl(void (*function)(void*),void *object,void *dso)
{
 (void)dso;if(!function)return -1;
 struct context *c=get_context();if(c->dtor_count>=256)return -1;
 struct dtor *d=malloc(sizeof(*d));if(!d)return -1;
 d->function=function;d->object=object;d->next=c->dtors;c->dtors=d;++c->dtor_count;return 0;
}
int __cxa_thread_atexit(void (*function)(void*),void *object,void *dso)
{return __cxa_thread_atexit_impl(function,object,dso);}
