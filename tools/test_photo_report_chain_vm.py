"""Exercise native capture-to-report transitions with fake IO, no board access."""
import base64
from cloud_radio_stage_audit import ROOT, remote
source=(ROOT/'app/k7agent/cloud/src/board_speech_bridge.c').read_text(encoding='utf-8')
body='static int photo_prompts('+source.split('static int photo_prompts(',1)[1].split('/* Stage checks',1)[0]
test=r'''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <inttypes.h>
#include <pthread.h>
#include <unistd.h>
#define CONFIG_EXAMPLES_K7HOST_TRACK 1
#include "device_photo_prompts.h"
static unsigned mask=7,phase,uploads,reports;
static int upload_error,report_error,resume_error;
static unsigned resumes;
static atomic_uint device_epoch=9;
static atomic_bool tts_cancelled;
static pthread_mutex_t tts_lock=PTHREAD_MUTEX_INITIALIZER;
static int k7_pipeline_hold_revision(unsigned *revision){*revision=3;return 0;}
static int k7_pipeline_resume_tracking(unsigned revision){assert(revision==3 && phase==5);resumes++;return resume_error;}
static char latest_report_task[37]="11111111-1111-4111-8111-111111111111";
static int k7_photo_native_status(uint32_t *epoch,unsigned *done){*epoch=2;*done=mask;return 0;}
static int k7_pipeline_voice_mode_status(unsigned mode){return mode==0 || (mode==1 && resumes)?0:-EBUSY;}
static int board_speech(const char *key,const char *ip,const unsigned *epoch){
 (void)ip;assert(*epoch==9);
 if(!strcmp(key,"right_saved")){assert(phase==0);phase=1;}
 else if(!strcmp(key,"capture_retained")){assert(phase==1);phase=2;}
 else if(!strcmp(key,"upload_accepted")){assert(phase==3);phase=4;}
 else {assert(!strcmp(key,"upload_failed") && phase==3);phase=99;}
 return 0;
}
static int photo_upload(const char *ip,unsigned command,uint32_t epoch){
 (void)ip;assert(command==9 && epoch==2 && phase==2);uploads++;phase=3;return upload_error;
}
static int report_play(const char *ip,const char *task,unsigned epoch){
 (void)ip;assert(epoch==9 && phase==4 && !strcmp(task,latest_report_task));phase=5;reports++;return report_error;
}
'''+body+r'''
int main(void){
 struct k7_photo_prompt_state state={2,3};
 assert(photo_prompts("gateway",9,&state)==0);
 assert(phase==5 && uploads==1 && reports==1 && state.done==7);
 assert(photo_prompts("gateway",9,&state)==0 && uploads==1 && reports==1);
 state=(struct k7_photo_prompt_state){2,3};phase=0;upload_error=-EIO;
 assert(photo_prompts("gateway",9,&state)==-EIO);
 assert(phase==99 && reports==1);
 state=(struct k7_photo_prompt_state){3,0};phase=0;
 assert(photo_prompts("gateway",9,&state)==-ESTALE && phase==0 && reports==1);
 assert(resumes==1);
 state=(struct k7_photo_prompt_state){2,3};phase=0;upload_error=0;report_error=-EIO;
 assert(photo_prompts("gateway",9,&state)==-EIO && resumes==1);
 state=(struct k7_photo_prompt_state){2,3};phase=0;report_error=0;atomic_store(&tts_cancelled,true);
 assert(photo_prompts("gateway",9,&state)==-ECANCELED && resumes==1);
 state=(struct k7_photo_prompt_state){2,3};phase=0;atomic_store(&tts_cancelled,false);resume_error=-ECANCELED;
 assert(photo_prompts("gateway",9,&state)==-ECANCELED && resumes==2);
 puts("PASS: successful report resumes; failed/cancelled/stale paths do not override stop");
}
'''
files={'test.c':test.encode(),
 'device_photo_prompts.h':(ROOT/'app/k7agent/cloud/include/device_photo_prompts.h').read_bytes(),
 'device_photo_prompts.c':(ROOT/'app/k7agent/cloud/src/device_photo_prompts.c').read_bytes()}
payload={k:base64.b64encode(v).decode() for k,v in files.items()}
result=remote('''import pathlib,base64,subprocess,tempfile
with tempfile.TemporaryDirectory(prefix='k7-report-chain-') as directory:
 p=pathlib.Path(directory)
 for name,data in %r.items():(p/name).write_bytes(base64.b64decode(data))
 for optimization in ('-O0','-O2'):
  subprocess.check_call(['gcc',optimization,'-Wall','-Wextra','-Werror','test.c','device_photo_prompts.c','-o','test'],cwd=p)
  subprocess.check_call([str(p/'test')],cwd=p)
'''%payload)
(ROOT/'evidence/report-speech-20260917/native-photo-report-resume-chain.txt').write_bytes(result)
print(result.decode())
