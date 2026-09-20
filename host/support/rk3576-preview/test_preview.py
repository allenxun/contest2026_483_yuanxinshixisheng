from pathlib import Path
import subprocess
w=Path('/home/swl/openvela/work/rk3576-preview')
source=r'''#include "k7_preview.h"
#include <assert.h>
#include <errno.h>
#include <stdint.h>
int main(void){uint8_t data[160*120*3];for(int i=0;i<(int)sizeof(data);i++)data[i]=(uint8_t)(i*37+11);
assert(k7_preview_emit(data,sizeof(data),42)==0);assert(k7_preview_emit(0,sizeof(data),1)==-EINVAL);
assert(k7_preview_emit(data,sizeof(data)-1,1)==-EINVAL);}
'''
(w/'test_preview.c').write_text(source)
subprocess.run(['gcc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-g','-c',
                '-I.','-I../../external/libjpeg-turbo/libjpeg-turbo','k7_preview.c','test_preview.c',
                ],cwd=w,check=True)
print('PASS thumbnail encoder and API compile with Wall/Wextra/Werror; board link/runtime pending')
