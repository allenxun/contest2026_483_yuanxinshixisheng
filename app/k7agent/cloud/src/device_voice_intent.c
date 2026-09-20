#include "device_voice_intent.h"
#include "../../../k7radio/cJSON.h"
#include <errno.h>
#include <math.h>
#include <string.h>

static enum k7_voice_intent command(const char *text)
{
  char normalized[129];size_t used=0;
  for(size_t i=0;text[i];)
    {
      unsigned char ch=(unsigned char)text[i];
      if(ch==' ' || ch=='\t' || ch=='\r' || ch=='\n' ||
         ch==',' || ch=='.' || ch=='!' || ch=='?'){i++;continue;}
      const char *marks[]={"，","。","！","？","　"};
      int skip=0;
      for(unsigned k=0;k<sizeof(marks)/sizeof(marks[0]);k++)
        if(!strncmp(text+i,marks[k],strlen(marks[k])))
          {i+=strlen(marks[k]);skip=1;break;}
      if(skip)continue;
      if(used==sizeof(normalized)-1)return K7_VOICE_NONE;
      normalized[used++]=(ch>='A' && ch<='Z')?(char)(ch-'A'+'a'):text[i];i++;
    }
  normalized[used]=0;
  if(strstr(normalized,"停止云台") || strstr(normalized,"停止测肤"))return K7_VOICE_STOP;
  if(strstr(normalized,"停止播报"))return K7_VOICE_QUIET;
  if(strstr(normalized,"不要") || strstr(normalized,"别启动") || strstr(normalized,"取消启动"))return K7_VOICE_NONE;
  if(!strncmp(normalized,"你好",strlen("你好")))return K7_VOICE_TRACK;
  if(!strcmp(normalized,"皮肤检测") || !strcmp(normalized,"开始皮肤检测") ||
     !strcmp(normalized,"测肤") || !strcmp(normalized,"开始测肤"))return K7_VOICE_PHOTO;
  if(!strcmp(normalized,"停止云台") || !strcmp(normalized,"停止测肤"))return K7_VOICE_STOP;
  if(!strcmp(normalized,"停止播报"))return K7_VOICE_QUIET;
  return K7_VOICE_NONE;
}

int k7_voice_event(struct k7_voice_result *out,const char *json,size_t size)
{
  if(!out || !json || !size || size>8192 || out->completed ||
     memchr(json,0,size))return -EINVAL;
  /* cJSON strings are NUL terminated: reject an escaped NUL before decoding. */
  for(size_t i=0;i+6<=size;i++)
    if(!memcmp(json+i,"\\u0000",6))return -EINVAL;
  const char *end=NULL;
  cJSON *root=cJSON_ParseWithLengthOpts(json,size,&end,0);
  int rc=-EINVAL;
  if(!root || !cJSON_IsObject(root))goto done;
  while(end<json+size && (*end==' '||*end=='\n'||*end=='\r'||*end=='\t'))end++;
  if(end!=json+size)goto done;
  for(cJSON *a=root->child;a;a=a->next)
    for(cJSON *b=a->next;b;b=b->next)
      if(!strcmp(a->string,b->string))goto done;
  cJSON *type=cJSON_GetObjectItemCaseSensitive(root,"type");
  if(!cJSON_IsString(type))goto done;
  if(!strcmp(type->valuestring,"partial")){rc=0;goto done;}
  if(!strcmp(type->valuestring,"completed")){out->completed=1;rc=0;goto done;}
  if(strcmp(type->valuestring,"final"))goto done;
  cJSON *text=cJSON_GetObjectItemCaseSensitive(root,"text");
  cJSON *id=cJSON_GetObjectItemCaseSensitive(root,"sentence_id");
  if(!cJSON_IsString(text) || !cJSON_IsNumber(id) ||
     !isfinite(id->valuedouble) || id->valuedouble<0 ||
     id->valuedouble>2147483647 || floor(id->valuedouble)!=id->valuedouble)goto done;
  enum k7_voice_intent intent=command(text->valuestring);
  if(out->finals>=32)goto done;
  if(!intent || (out->finals && intent!=out->intent))out->ambiguous=1;
  out->intent=intent;out->finals++;rc=0;
done:
  cJSON_Delete(root);return rc;
}

enum k7_voice_intent k7_voice_result_intent(const struct k7_voice_result *result)
{
  return result && result->completed && result->finals && !result->ambiguous
    ? result->intent : K7_VOICE_NONE;
}
