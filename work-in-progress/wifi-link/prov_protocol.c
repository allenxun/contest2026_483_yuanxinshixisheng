/* SPDX-License-Identifier: Apache-2.0 */
#include "prov_protocol.h"
#include "cJSON.h"
#include <string.h>
#include <errno.h>
#include <stdlib.h>
union prov_alloc_header { max_align_t alignment; size_t size; };
static void *prov_json_alloc(size_t n)
{
 if(n>SIZE_MAX-sizeof(union prov_alloc_header)) return NULL;
 union prov_alloc_header *p=malloc(sizeof(*p)+n);
 if(!p) return NULL;
 p->size=n;return p+1;
}
static void prov_json_free(void *ptr)
{
 if(!ptr) return;
 union prov_alloc_header *p=(union prov_alloc_header *)ptr-1;
 prov_zero(ptr,p->size);prov_zero(p,sizeof(*p));free(p);
}
void prov_protocol_init(void)
{ cJSON_Hooks hooks={prov_json_alloc,prov_json_free};cJSON_InitHooks(&hooks); }
void prov_zero(void *p,size_t n)
{ volatile unsigned char *v=p;while(n--) *v++=0; }
void prov_rx_reset(struct prov_rx *r)
{ prov_zero(r,sizeof(*r)); }
int prov_rx_feed(struct prov_rx *r,const void *data,size_t n,uint32_t now)
{
 const unsigned char *p=data;
 if (!r || !data || !n || n>20) return -EINVAL;
 if ((r->used || r->discard) && (uint32_t)(now-r->started)>=10000)
   { prov_rx_reset(r);return -ETIMEDOUT; }
 if (!r->used && !r->discard) r->started=now;
 if (r->discard)
   { if (memchr(p,'\n',n)) prov_rx_reset(r);return -EMSGSIZE; }
 if (!r->used && n==1 && p[0]=='X')
   { r->data[0]='X';r->data[1]=0;r->used=1;return 1; }
 if (r->used+n>PROV_MAX_CMD)
   { uint32_t began=r->started;prov_rx_reset(r);r->started=began;r->discard=1;return -EMSGSIZE; }
 for (size_t i=0;i<n;i++)
   if (!p[i] || (p[i]=='\n' && i!=n-1))
     { prov_rx_reset(r);return -EPROTO; }
 memcpy(r->data+r->used,p,n);r->used+=n;r->data[r->used]=0;
 return p[n-1]=='\n' ? 1:0;
}
static void wipe_json(cJSON *item)
{
 for (;item;item=item->next)
   { if(item->child) wipe_json(item->child);
     if(item->valuestring) prov_zero(item->valuestring,strlen(item->valuestring));
     if(item->string) prov_zero(item->string,strlen(item->string)); }
}
int prov_parse(const char *text,struct prov_request *out)
{
 int ret=-EINVAL;
 if(!text || !out) return ret;
 memset(out,0,sizeof(*out));
 if(!strcmp(text,"X")) { out->command=PROV_SCAN;return 0; }
 if(strlen(text)>PROV_MAX_CMD || strstr(text,"\\u0000")) return ret;
 cJSON *root=cJSON_ParseWithOpts(text,NULL,1);
 if(!root) return ret;
 if(!cJSON_IsObject(root)) goto done;
 cJSON *cmd=cJSON_GetObjectItemCaseSensitive(root,"cmd");
 cJSON *id=cJSON_GetObjectItemCaseSensitive(root,"id");
 cJSON *v=cJSON_GetObjectItemCaseSensitive(root,"v");
 if(!cJSON_IsString(cmd) || !cJSON_IsNumber(id) || !cJSON_IsNumber(v) ||
    v->valuedouble!=1 || id->valuedouble<1 || id->valuedouble>65535 ||
    id->valuedouble!=(double)id->valueint) goto done;
 for(cJSON *a=root->child;a;a=a->next)
   { if(!a->string || (strcmp(a->string,"v") && strcmp(a->string,"id") &&
      strcmp(a->string,"cmd") && strcmp(a->string,"ssid_b64") && strcmp(a->string,"password"))) goto done;
     for(cJSON *b=a->next;b;b=b->next) if(!strcmp(a->string,b->string)) goto done;
   }
 if(!strcmp(cmd->valuestring,"scan")) out->command=PROV_SCAN;
 else if(!strcmp(cmd->valuestring,"status")) out->command=PROV_STATUS;
 else if(!strcmp(cmd->valuestring,"connect")) out->command=PROV_CONNECT;
 else goto done;
 out->id=(unsigned int)id->valueint;ret=0;
done:
 wipe_json(root);cJSON_Delete(root);return ret;
}
void prov_base64(const uint8_t *p,size_t n,char *out)
{
 static const char table[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
 size_t k=0;
 for(size_t i=0;i<n;i+=3)
   { unsigned int v=(unsigned int)p[i]<<16;
     if(i+1<n) v|=(unsigned int)p[i+1]<<8;
     if(i+2<n) v|=p[i+2];
     out[k++]=table[v>>18];out[k++]=table[(v>>12)&63];
     out[k++]=i+1<n?table[(v>>6)&63]:'=';out[k++]=i+2<n?table[v&63]:'=';
   }
 out[k]=0;
}
