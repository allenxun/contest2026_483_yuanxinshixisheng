from pathlib import Path
r=Path('/home/swl/openvela');w=r/'work/rk3576-preview'
s=(r/'apps/examples/k7host/k7_pipeline.c').read_text()
a='int viewret=k7_preview_emit(slot->data,slot->bytes,slot->sequence);'
b='int viewret=k7_preview_emit(p->rgb,result.bytes,slot->sequence);'
assert s.count(a)==1;s=s.replace(a,b)
a='printf("VIEW SKIP q=%u n=%u result=%d\\n",slot->sequence,\n                       (unsigned int)slot->bytes,viewret);'
b='printf("VIEW SKIP q=%u rgb=%u result=%d\\n",slot->sequence,\n                       (unsigned int)result.bytes,viewret);'
assert s.count(a)==1;s=s.replace(a,b)
(w/'k7_pipeline.thumbnail.c').write_text(s)
print('Prepared thumbnail pipeline source; not installed')
