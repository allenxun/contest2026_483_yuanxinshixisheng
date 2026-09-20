#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "../../app/k7agent/cloud/include/device_voice_intent.h"
static int event(struct k7_voice_result *r,const char *s)
{ return k7_voice_event(r,s,strlen(s)); }
int main(void)
{
  struct k7_voice_result r={0};
  assert(!event(&r,"{\"type\":\"partial\",\"text\":\"你好OpenVela\"}"));
  assert(k7_voice_result_intent(&r)==K7_VOICE_NONE);
  assert(!event(&r,"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"你好OpenVela。\"}"));
  assert(k7_voice_result_intent(&r)==K7_VOICE_NONE);
  assert(!event(&r,"{\"type\":\"completed\"}"));
  assert(k7_voice_result_intent(&r)==K7_VOICE_TRACK);
  assert(event(&r,"{\"type\":\"completed\"}")<0);
  const char *bad[]={
    "{\"type\":\"final\",\"type\":\"completed\"}",
    "{\"type\":\"completed\"}junk",
    "{\"type\":\"final\",\"sentence_id\":-1,\"text\":\"你好OpenVela\"}",
    "{\"type\":\"final\",\"sentence_id\":1.5,\"text\":\"你好OpenVela\"}",
    "{\"type\":\"final\",\"sentence_id\":0,\"text\":\"你好OpenVela\\u0000不要\"}",
    "{\"type\":\"error\"}"};
  for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++)
    {r=(struct k7_voice_result){0};assert(event(&r,bad[i])<0);}
  const char *photo_commands[]={"开始测肤","皮肤检测。","开始皮肤检测"};
  for(unsigned i=0;i<sizeof(photo_commands)/sizeof(photo_commands[0]);i++)
    {
      char json[300];r=(struct k7_voice_result){0};
      snprintf(json,sizeof(json),"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"%s\"}",photo_commands[i]);
      assert(!event(&r,json));assert(k7_voice_result_intent(&r)==K7_VOICE_NONE);
      assert(!event(&r,"{\"type\":\"completed\"}"));
      assert(k7_voice_result_intent(&r)==K7_VOICE_PHOTO);
    }
  const char *noncommands[]={"不要你好OpenVela","今天天气怎么样","启动","启动openvela","openvela","云台已启动","他说你好","你好不要启动","不要皮肤检测","皮肤检测是什么意思","开始侧敷","开始测幅",""};
  for(unsigned i=0;i<sizeof(noncommands)/sizeof(noncommands[0]);i++)
    {
      char json[300];r=(struct k7_voice_result){0};
      snprintf(json,sizeof(json),"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"%s\"}",noncommands[i]);
      assert(!event(&r,json));assert(!event(&r,"{\"type\":\"completed\"}"));
      assert(k7_voice_result_intent(&r)==K7_VOICE_NONE);
    }
  r=(struct k7_voice_result){0};
  assert(!event(&r,"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"你好OpenVela\"}"));
  assert(!event(&r,"{\"type\":\"final\",\"sentence_id\":1,\"text\":\"停止云台\"}"));
  assert(!event(&r,"{\"type\":\"completed\"}"));
  assert(k7_voice_result_intent(&r)==K7_VOICE_NONE);
  const char *start_commands[]={"你好。","你好openvela","你好openvlea","你好 Open Vela","你好小维","你好联网"};
  for(unsigned i=0;i<sizeof(start_commands)/sizeof(start_commands[0]);i++)
    {
      char json[300];r=(struct k7_voice_result){0};
      snprintf(json,sizeof(json),"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"%s\"}",start_commands[i]);
      assert(!event(&r,json));assert(!event(&r,"{\"type\":\"completed\"}"));
      assert(k7_voice_result_intent(&r)==K7_VOICE_TRACK);
    }
  r=(struct k7_voice_result){0};
  assert(!event(&r,"{\"type\":\"final\",\"sentence_id\":0,\"text\":\"你好openvela停止云台\"}"));
  assert(!event(&r,"{\"type\":\"completed\"}"));
  assert(k7_voice_result_intent(&r)==K7_VOICE_STOP);
  puts("native ASR intent guards PASS");
}
