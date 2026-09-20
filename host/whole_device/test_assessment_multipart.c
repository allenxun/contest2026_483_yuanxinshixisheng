#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "../../app/k7agent/cloud/include/assessment_multipart.h"
int main(void)
{
  const unsigned char jpeg[]={255,216,0,1,2,255,217};
  struct k7_upload_image images[3]={{jpeg,7},{jpeg,7},{jpeg,7}};
  struct k7_assessment_body b;unsigned char all[4096],part[4096];
  const char *token="0123456789abcdef0123456789abcdef";
  assert(k7_assessment_body_init(&b,"capture","consent\r\n",token,images)==-EINVAL);
  assert(k7_assessment_body_init(&b,"capture","consent","invalid",images)==-EINVAL);
  assert(k7_assessment_body_init(&b,"capture","consent",token,images)==0);
  assert(b.total<sizeof(all));
  assert(k7_assessment_body_read(&b,0,all,sizeof(all))==(ssize_t)b.total);
  for(size_t chunk=1;chunk<=1024;chunk*=4) {
    size_t n=0;
    while(n<b.total){ssize_t count=k7_assessment_body_read(&b,n,part+n,chunk);assert(count>0);n+=(size_t)count;}
    assert(n==b.total&&!memcmp(all,part,n));
  }
  assert(k7_assessment_body_read(&b,b.total,part,1)==0);
  assert(k7_assessment_body_read(&b,b.total+1,part,1)==-EINVAL);
  FILE *f=fopen("multipart.bin","wb");assert(f);assert(fwrite(all,1,b.total,f)==b.total);fclose(f);
  puts("bounded multipart reads PASS; fixture only, no upload");
}
