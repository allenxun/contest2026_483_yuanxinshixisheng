from pathlib import Path
import subprocess
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';old=r/'work/rk3576-track-v22'
track=(old/'test_track.c').read_text().replace('#include "k7_track.h"','#include <k7_track.h>')
track=track.replace('{false,30,sx,sy,TRACK_XY}','{false,30,sx,sy,TRACK_XY,false}')
track=track.replace('{true,30,1,1,TRACK_XY}','{true,30,1,1,TRACK_XY,false}')
track=track.replace('{true,30,1,1,axis}', '{true,30,1,1,axis,false}')
(w/'test_track.c').write_text(track)
pipe=(old/'test_pipeline.c').read_text().replace('#include "k7_pipeline.h"','#include <k7_pipeline.h>')
pipe=pipe.replace('{run,30,1,1,TRACK_Y}','{run,30,1,1,TRACK_Y,false}')
pipe=pipe.replace('struct k7_yunet_s {int unused;};',
'''int k7_preview_emit(const uint8_t *jpeg,size_t size,unsigned int sequence)
{(void)jpeg;(void)size;(void)sequence;return 0;}
struct k7_yunet_s {int unused;};''')
(w/'test_pipeline.c').write_text(pipe)
flags=['gcc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g']
with (w/'tests-async-regression.log').open('w') as log:
 def run(a):
  log.write('$ '+' '.join(a)+'\n');log.flush();subprocess.run(a,cwd=w,stdout=log,stderr=subprocess.STDOUT,check=True)
 run(flags+['-I../../apps/examples/k7host','../../apps/examples/k7host/k7_track.c','test_track.c','-lm','-o','test_track'])
 run(['./test_track'])
 run(flags+['-D_POSIX_C_SOURCE=200809L','-DCONFIG_EXAMPLES_K7HOST_YUNET','-DCONFIG_EXAMPLES_K7HOST_TRACK',
  '-DGIMBAL_PORT="/tmp/k7-v23-pipeline-test-uart"','-I../../apps/examples/k7host','-I../../apps/examples/gimbal',
  '../../apps/examples/k7host/k7_preview_queue.c','../../apps/examples/k7host/k7_pipeline.c','../../apps/examples/k7host/k7_track.c',
  '../../apps/examples/gimbal/gimbal_link.c','test_pipeline.c','-pthread','-lm','-o','test_pipeline'])
 run(['./test_pipeline'])
print('PASS v23 controller/pipeline ASan/UBSan regressions')
