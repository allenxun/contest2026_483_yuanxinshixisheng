#include <assert.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
#include <stdatomic.h>
#include "../../app/k7host/k7_photo_store.h"
struct stress {struct k7_photo_store *store;atomic_uint epoch;atomic_int finished;};
static void *reset_writer(void *arg)
{
  struct stress *s=arg;
  for(unsigned e=3;e<503;e++)
    {
      unsigned char jpeg[]={0xff,0xd8,(unsigned char)e,0xff,0xd9};
      assert(!k7_photo_store_begin(s->store,e));
      atomic_store(&s->epoch,e);
      for(unsigned i=0;i<3;i++)
        {
          struct k7_photo_record r={.epoch=e,.sequence=i+1,.side=1u<<i,.bytes=5};
          assert(!k7_photo_store_put(s->store,&r,jpeg));
        }
    }
  atomic_store(&s->finished,1);return NULL;
}
static void *copy_reader(void *arg)
{
  struct stress *s=arg;
  do {
    unsigned e=atomic_load(&s->epoch);
    for(unsigned i=0;i<3;i++)
      {
        struct k7_photo_record r;unsigned char bytes[20];
        int rc=k7_photo_store_copy(s->store,e,1u<<i,&r,bytes,sizeof(bytes));
        assert(rc==0||rc==-ESTALE||rc==-ENOENT);
        if(!rc){assert(r.epoch==e && r.side==(1u<<i));assert(bytes[2]==(unsigned char)e);}
      }
  }while(!atomic_load(&s->finished));
  return NULL;
}
int main(void)
{
  unsigned char jpeg[]={0xff,0xd8,1,2,0xff,0xd9},copy[20]={0};
  struct k7_photo_record r={.epoch=1,.sequence=7,.side=1,.bytes=sizeof(jpeg)},saved={0};
  assert(!k7_photo_store_create(1024*1024+1));
  struct k7_photo_store *s=k7_photo_store_create(20);assert(s);
  assert(k7_photo_store_put(s,&r,jpeg)==-ESTALE);
  assert(k7_photo_store_begin(s,1)==0);
  r.side=2;assert(k7_photo_store_put(s,&r,jpeg)==-EINVAL);r.side=1;
  assert(k7_photo_store_put(s,&r,jpeg)==0);
  assert(k7_photo_store_put(s,&r,jpeg)==0);
  jpeg[2]=9;assert(k7_photo_store_put(s,&r,jpeg)==-EEXIST);
  assert(k7_photo_store_copy(s,1,1,&saved,copy,sizeof(copy))==0);
  assert(copy[2]==1 && saved.sequence==7); /* producer buffer was recycled */
  assert(k7_photo_store_copy(s,1,1,&saved,copy,2)==-EMSGSIZE);
  r.side=2;assert(k7_photo_store_put(s,&r,jpeg)==-ESTALE);
  r.sequence=8;assert(k7_photo_store_put(s,&r,jpeg)==0);
  r.side=4;r.sequence=9;assert(k7_photo_store_put(s,&r,jpeg)==0);
  assert(k7_photo_store_complete(s,1)==1);
  assert(k7_photo_store_begin(s,1)==-ESTALE);
  assert(k7_photo_store_begin(s,2)==0);
  assert(k7_photo_store_copy(s,1,1,&saved,copy,sizeof(copy))==-ESTALE);
  assert(k7_photo_store_copy(s,2,1,&saved,copy,sizeof(copy))==-ENOENT);
  assert(copy[2]==1); /* caller upload copy survives invalidation */
  assert(k7_photo_store_complete(s,2)==0);
  assert(k7_photo_store_put(s,&r,jpeg)==-ESTALE);
  struct stress stress={.store=s};pthread_t writer,reader;
  atomic_store(&stress.epoch,2);
  assert(!pthread_create(&reader,NULL,copy_reader,&stress));
  assert(!pthread_create(&writer,NULL,reset_writer,&stress));
  assert(!pthread_join(writer,NULL));assert(!pthread_join(reader,NULL));
  assert(k7_photo_store_complete(s,502)==1);
  k7_photo_store_destroy(s);
  puts("photo RAM retention PASS (not durable, not hardware photos)");
}
