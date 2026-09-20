"""Read and preserve SDK audio predecessors before a scoped integration."""
import base64,difflib,json
from cloud_radio_stage_audit import ROOT,remote
paths=['pio.c','pio.h','k7sound_main.c','CMakeLists.txt','capture_stream.h','stream_ring.c','stream_ring.h']
code='''import pathlib,json,base64
root=pathlib.Path('/home/swl/openvela/apps/examples/k7sound')
print(json.dumps({n:base64.b64encode((root/n).read_bytes()).decode() if (root/n).exists() else None for n in %r}))
''' % paths
data=json.loads(remote(code))
out=ROOT/'evidence/capture-stream-20260914/sdk-before'
out.mkdir(parents=True,exist_ok=True)
for name,encoded in data.items():
    if encoded is None: continue
    content=base64.b64decode(encoded)
    p=out/name
    if p.exists() and p.read_bytes()!=content:raise RuntimeError('predecessor changed')
    p.write_bytes(content)
    diff=''.join(difflib.unified_diff(content.decode().splitlines(True),(ROOT/'app/k7sound'/name).read_text().splitlines(True),fromfile=name+' SDK',tofile='project'))
    print(diff)
(out.parent/'predecessors.json').write_text(json.dumps(data)+'\n')
