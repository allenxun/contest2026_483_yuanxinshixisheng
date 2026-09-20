"""Compile actual endpoint/callback code with fake samples, without hardware."""
import base64
from cloud_radio_stage_audit import ROOT,remote
source=(ROOT/'app/k7agent/cloud/src/board_speech_bridge.c').read_text(encoding='utf-8')
callback='static int command_sample('+source.split('static int command_sample(',1)[1].split('static void *record',1)[0]
test=r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include "stream_ring.h"
#include "command_endpoint.h"
static atomic_bool photo_prompt_pending;
struct live {struct k7_stream_ring ring;int chat;struct k7_command_endpoint endpoint;int capture_reason,stage_priority;};
'''+callback+r'''
int main(void){
 static struct live p;int rc=0;unsigned sample=0;uint8_t out[640];uint32_t seq;
 while(!rc && sample<48000){int16_t s=sample<16000?1000:0;rc=command_sample(&p,(uint32_t)(uint16_t)s<<16,0);sample++;}
 assert(rc==1 && p.capture_reason==1 && sample==22400 && p.ring.produced==70);
 for(unsigned i=0;i<70;i++){
  assert(k7_stream_ring_take(&p.ring,out,&seq)==1 && seq==i);
  assert(out[0]==(i<50?0xe8:0) && out[1]==(i<50?3:0));
 }
 assert(k7_stream_ring_take(&p.ring,out,&seq)==0);
 p=(struct live){0};p.stage_priority=1;atomic_store(&photo_prompt_pending,true);
 for(unsigned i=0;i<319;i++)assert(command_sample(&p,0,0)==0);
 assert(command_sample(&p,0,0)==1 && p.capture_reason==2 && p.ring.produced==1);
 p=(struct live){0};p.chat=1;p.stage_priority=1;
 for(unsigned i=0;i<48000;i++)assert(command_sample(&p,0,0)==0);
 assert(p.ring.produced==150 && !p.capture_reason);
 puts("PASS: exact leading PCM/sequence retained, stage priority at frame boundary, chat unchanged");
}
'''
files={'test.c':test.encode(),
 'endpoint_test.c':(ROOT/'host/whole_device/test_command_endpoint.c').read_bytes().replace(b'../../app/k7agent/cloud/src/command_endpoint.h',b'command_endpoint.h'),
 'command_endpoint.h':(ROOT/'app/k7agent/cloud/src/command_endpoint.h').read_bytes(),
 'stream_ring.c':(ROOT/'app/k7sound/stream_ring.c').read_bytes(),
 'stream_ring.h':(ROOT/'app/k7sound/stream_ring.h').read_bytes()}
payload={p:base64.b64encode(data).decode() for p,data in files.items()}
result=remote('''import pathlib,tempfile,base64,subprocess
with tempfile.TemporaryDirectory(prefix='k7-latency-') as folder:
 p=pathlib.Path(folder)
 for name,data in %r.items():(p/name).write_bytes(base64.b64decode(data))
 for opt in ('-O0','-O2'):
  for source,extra in [('test.c',['stream_ring.c']),('endpoint_test.c',[])]:
   subprocess.check_call(['gcc','-std=c11',opt,'-Wall','-Wextra','-Werror',source]+extra+['-o','test'],cwd=p)
   subprocess.check_call([str(p/'test')],cwd=p)
'''%payload)
folder=ROOT/'evidence/command-latency-20260917';folder.mkdir(exist_ok=True)
(folder/'endpoint-tests.txt').write_bytes(result)
print(result.decode())
