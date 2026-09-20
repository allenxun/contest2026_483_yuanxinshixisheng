#include "recipe.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
int main(void) {
  struct sai_recipe r, saved;
  unsigned i;
  assert(sai_recipe(4096000, &r)==0);
  assert(r.item[0].offset==8 && r.item[0].value==0x00400def);
  assert(r.item[1].offset==0x68 && r.item[1].value==2);
  assert(r.item[2].offset==4 && r.item[2].value==0x0100f01f);
  assert(r.item[3].offset==0x18 && r.item[3].value==56);
  assert(r.item[4].offset==0x24 && r.item[4].value==0x000f0000);
  assert(r.rxdr_offset==0x34 && r.dma_bus_bytes==4 && r.dma_maxburst==8);
  for(i=0;i<5;i++) assert(!(r.item[i].value & ~r.item[i].mask));
  saved=r;
  assert(sai_recipe(0,&r)<0 && !memcmp(&r,&saved,sizeof r));
  assert(sai_recipe(4096001,&r)<0 && !memcmp(&r,&saved,sizeof r));
  assert(sai_recipe(512000u*4097u,&r)<0 && !memcmp(&r,&saved,sizeof r));
  assert(sai_recipe(4096000,NULL)<0);
  assert(sai_recipe(12288000,&r)==0 && r.item[3].value==184);
  assert(sai_recipe(512000,&r)==0 && r.item[3].value==0);
  assert(sai_recipe(512000u*4096u,&r)==0 && r.item[3].value==32760);
  puts("PASS: fixed recipe, mask bounds, exact clock division, invalid output preservation");
  puts("NOT_READY: no MMIO/DMA/codec/hardware executed");
  return 0;
}
