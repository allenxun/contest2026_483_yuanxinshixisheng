"""Compile the actual retry entry with fake storage/network; never access hardware."""
import base64
from cloud_radio_stage_audit import ROOT,remote
source=(ROOT/'app/k7agent/cloud/src/board_speech_bridge.c').read_text()
body=source.split('int k7cloud_photo_retry(',1)[1].split('static int photo_prompts',1)[0]
body='int k7cloud_photo_retry('+body
test=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <pthread.h>
#include <errno.h>
#include <stdio.h>
#define CONFIG_EXAMPLES_K7HOST_TRACK 1
static atomic_bool device_loop_busy,device_busy;
static atomic_uint device_epoch;
static pthread_mutex_t audio_owner=PTHREAD_MUTEX_INITIALIZER;
static unsigned mask=7,calls;
static int storage_error,mode_error,upload_error;
static int k7_photo_native_status(uint32_t *e,unsigned *d){*e=3;*d=mask;return storage_error;}
static int k7_pipeline_voice_mode_status(unsigned m){assert(m==0);return mode_error;}
static int photo_upload(const char *ip,unsigned command,uint32_t photo){(void)ip;assert(command==9 && photo==3);calls++;return upload_error;}
'''+body+r'''
int main(void){
 atomic_store(&device_epoch,9);
 atomic_store(&device_loop_busy,true);assert(k7cloud_photo_retry("test")==-EBUSY);assert(!calls);
 atomic_store(&device_loop_busy,false);atomic_store(&device_busy,true);
 assert(k7cloud_photo_retry("test")==-EBUSY);atomic_store(&device_busy,false);
 mask=3;assert(k7cloud_photo_retry("test")==-ENODATA);assert(!calls && !atomic_load(&device_busy));
 mask=7;mode_error=-ECANCELED;assert(k7cloud_photo_retry("test")==-ECANCELED);assert(!calls);
 mode_error=0;storage_error=-ENODEV;assert(k7cloud_photo_retry("test")==-ENODEV);assert(!calls);
 storage_error=0;upload_error=-EIO;assert(k7cloud_photo_retry("test")==-EIO);assert(calls==1);
 assert(!atomic_load(&device_busy));assert(!pthread_mutex_trylock(&audio_owner));pthread_mutex_unlock(&audio_owner);
 upload_error=0;assert(!k7cloud_photo_retry("test"));assert(calls==2 && mask==7);
 puts("photo retry guards PASS; retained set unchanged");
}
'''
encoded=base64.b64encode(test.encode()).decode()
print(remote('''import tempfile,pathlib,base64,subprocess
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d);(p/'test.c').write_bytes(base64.b64decode(%r))
 for opt in ['-O0','-O2']:
  subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',opt,'-pthread',str(p/'test.c'),'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True)
'''%encoded).decode())
