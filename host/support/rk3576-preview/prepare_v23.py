from pathlib import Path
import hashlib,json
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview';w.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
old=json.loads((r/'work/rk3576-track-v22/manifest-v22.json').read_text())['source_sha256']
plan=[]
def sub(s,a,b):
    assert s.count(a)==1,(a,s.count(a));return s.replace(a,b)
def change(path,fn):
    p=r/path;before=p.read_bytes();assert sha(before)==old[path],path
    backup=w/(p.name+'.v22');assert not backup.exists();backup.write_bytes(before)
    after=fn(before.decode()).encode();(w/p.name).write_bytes(after)
    plan.append(dict(target=path,local=p.name,old_sha256=sha(before),new_sha256=sha(after)))
def cmake(s):
    return sub(s,'    list(APPEND SRCS k7_track.c)','    list(APPEND SRCS k7_track.c k7_preview.c)')
change('apps/examples/k7host/CMakeLists.txt',cmake)
def header(s):
    return sub(s,'int limit, sign_x, sign_y; unsigned int axes;',
               'int limit, sign_x, sign_y; unsigned int axes; bool preview;')
change('apps/examples/k7host/k7_track.h',header)
def pipeline(s):
    s=sub(s,'#include "../gimbal/gimbal_link.h"',
          '#include "../gimbal/gimbal_link.h"\n#include "k7_preview.h"')
    s=sub(s,'      if (p->tracking)\n        track_observation(p, ret == 0 && face_ret == 0 ? &faces : NULL,\n                          slot->sequence, slot->published_us);',
'''      if (p->tracking)
        {
          track_observation(p, ret == 0 && face_ret == 0 ? &faces : NULL,
                            slot->sequence, slot->published_us);
          /* Preview is intentionally sampled after tracking. It uses the exact
           * compressed frame that produced this observation and never the
           * STM32 control UART. At most about two frames/s reach the console.
           */
          if (p->controller.config.preview && ret == 0 &&
              p->stats.track_observations % 4 == 1)
            {
              int viewret=k7_preview_emit(slot->data,slot->bytes,slot->sequence);
              if (viewret < 0)
                printf("VIEW SKIP q=%u n=%u result=%d\\n",slot->sequence,
                       (unsigned int)slot->bytes,viewret);
            }
        }''')
    return s
change('apps/examples/k7host/k7_pipeline.c',pipeline)
def app(s):
    s=sub(s,'if (argc >= 2 && !strcmp(argv[1], "track"))',
          'if (argc >= 2 && (!strcmp(argv[1], "track") || !strcmp(argv[1], "preview")))')
    s=sub(s,'.sign_x=v[2],.sign_y=v[3],.axes=axes};',
          '.sign_x=v[2],.sign_y=v[3],.axes=axes,\n        .preview=!strcmp(argv[1],"preview")};')
    s=sub(s,'puts("TRACK: k7host track dry|run [1..30 seconds] [1..50 limit] [-1|1 X] [-1|1 Y] [xy|x|y]");',
'''puts("TRACK: k7host track dry|run [1..30 seconds] [1..50 limit] [-1|1 X] [-1|1 Y] [xy|x|y]");
  puts("VIEW: k7host preview dry|run [1..30 seconds] [1..50 limit] [-1|1 X] [-1|1 Y] [xy|x|y]");''')
    return s
change('apps/examples/k7host/k7host_main.c',app)
for name in ['k7_preview.c','k7_preview.h']:
    dest='apps/examples/k7host/'+name;p=r/dest;assert not p.exists(),dest
    data=(w/name).read_bytes();plan.append(dict(target=dest,local=name,old_sha256='',new_sha256=sha(data)))
(w/'install-plan.json').write_text(json.dumps(plan,indent=2))
print('Prepared',len(plan),'v23 preview source changes; not installed')
