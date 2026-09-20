#include <assert.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include "../../app/k7agent/cloud/include/device_photo_prompts.h"
int main(void)
{
  struct k7_photo_prompt_state state={0};const char *keys[4];
  assert(k7_photo_prompt_plan(&state,1,0,keys)==1);
  assert(!strcmp(keys[0],"front_aligning"));
  state=(struct k7_photo_prompt_state){1,0};
  assert(k7_photo_prompt_plan(&state,1,0,keys)==0);
  assert(k7_photo_prompt_plan(&state,1,1,keys)==2);
  assert(!strcmp(keys[0],"front_saved") && !strcmp(keys[1],"left_aligning"));
  state.done=1;
  assert(k7_photo_prompt_plan(&state,1,3,keys)==2);
  assert(!strcmp(keys[0],"left_saved") && !strcmp(keys[1],"right_aligning"));
  state.done=3;
  assert(k7_photo_prompt_plan(&state,1,7,keys)==2);
  assert(!strcmp(keys[0],"right_saved") && !strcmp(keys[1],"capture_retained"));
  state.done=7;
  assert(k7_photo_prompt_plan(&state,1,7,keys)==0);
  state.done=1;
  assert(k7_photo_prompt_plan(&state,1,7,keys)==3);
  assert(!strcmp(keys[0],"left_saved") && !strcmp(keys[1],"right_saved"));
  assert(!strcmp(keys[2],"capture_retained")); /* never claims upload or durable save */
  assert(k7_photo_prompt_plan(&state,1,0,keys)==-EIO);
  assert(k7_photo_prompt_plan(&state,1,2,keys)==-EINVAL);
  assert(k7_photo_prompt_plan(&state,2,0,keys)==1);
  state.epoch=2;
  assert(k7_photo_prompt_plan(&state,1,7,keys)==-ESTALE);
  state=(struct k7_photo_prompt_state){0};
  assert(k7_photo_prompt_plan(&state,2,7,keys)==4);
  puts("native photo prompt transitions PASS");
}
