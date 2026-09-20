from pathlib import Path
import shutil,json,hashlib
r=Path('/home/swl/openvela'); w=r/'work/rk3576-preview'; a=r/'apps/examples/k7host'
changes={}
s=(a/'k7_preview.h').read_text().replace('const uint8_t *jpeg','const uint8_t *rgb')
s=s.replace('#endif','''struct k7_preview_queue_s;
int k7_preview_queue_start(struct k7_preview_queue_s **out);
void k7_preview_queue_submit(struct k7_preview_queue_s *, const uint8_t *, size_t, unsigned int);
int k7_preview_queue_stop(struct k7_preview_queue_s *);
#endif''');changes['k7_preview.h']=s
s=(a/'k7_pipeline.c').read_text()
s=s.replace('  bool tracking;','  bool tracking;\n  struct k7_preview_queue_s *preview;')
begin=s.index('          /* Preview is intentionally sampled')
end=s.index('\n        }\n#endif',begin)
s=s[:begin]+'''          /* Submit a private RGB copy; output never runs in this worker. */
          if (p->preview && ret == 0)
            k7_preview_queue_submit(p->preview,p->rgb,result.bytes,slot->sequence);'''+s[end:]
marker='  p->started_us = monotonic_us();'
s=s.replace(marker,'''#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  if (track && track->preview)
    {
      ret=k7_preview_queue_start(&p->preview);
      if (ret < 0) { ret=-ret; goto destroy_attr; }
    }
#endif
'''+marker)
s=s.replace('  if (ret) goto destroy_cond;\n  *out = p;', '''  if (ret)
    {
#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
      int stopped=k7_preview_queue_stop(p->preview);
      if (stopped < 0) return stopped;
#endif
      goto destroy_cond;
    }
  *out = p;''')
s=s.replace('  p->stats.elapsed_us =', '''#ifdef CONFIG_EXAMPLES_K7HOST_TRACK
  ret=k7_preview_queue_stop(p->preview);
  if (ret < 0) return ret;
#endif
  p->stats.elapsed_us =''')
changes['k7_pipeline.c']=s
changes['CMakeLists.txt']=(a/'CMakeLists.txt').read_text().replace('k7_track.c k7_preview.c','k7_track.c k7_preview.c k7_preview_queue.c')
changes['k7_preview_queue.c']=(w/'k7_preview_queue.c').read_text()
backup=w/'async-backup';backup.mkdir(exist_ok=False)
for name,s in changes.items():
 p=a/name
 if p.exists():shutil.copy2(p,backup/name)
 p.write_text(s)
(w/'async-install.json').write_text(json.dumps({n:hashlib.sha256((a/n).read_bytes()).hexdigest() for n in changes},indent=2))
print('Installed latest-only preview worker at priority 80; decoder remains 90')
