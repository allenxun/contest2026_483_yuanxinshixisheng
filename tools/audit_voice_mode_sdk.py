"""Capture SDK predecessors and show exact diff for review before syncing."""
import base64
import difflib
import hashlib
import json
from cloud_radio_stage_audit import ROOT, remote

FILES=['app/k7host/k7host_main.c','app/k7host/k7_pipeline.c',
       'app/k7host/k7_pipeline.h','app/k7host/k7_track.h']
if __name__ == '__main__':
    data=json.loads(remote('import pathlib,base64,json\nr=pathlib.Path("/home/swl/openvela/apps/examples")\nprint(json.dumps({p:base64.b64encode((r/p[4:]).read_bytes()).decode() for p in %r}))' % FILES))
    output=ROOT/'evidence/voice-mode-20260915'
    hashes={};diff=[]
    for rel,value in data.items():
        old=base64.b64decode(value);new=(ROOT/rel).read_bytes()
        path=output/'sdk-before'/rel;path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.read_bytes()!=old:raise RuntimeError('Predecessor changed: '+rel)
        path.write_bytes(old);hashes[rel]=hashlib.sha256(old).hexdigest()
        diff.extend(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),fromfile='sdk/'+rel,tofile=rel))
    (output/'sdk-before.json').write_text(json.dumps(hashes,indent=2)+'\n')
    (output/'sdk.diff').write_text(''.join(diff),encoding='utf8')
    print(''.join(diff))
