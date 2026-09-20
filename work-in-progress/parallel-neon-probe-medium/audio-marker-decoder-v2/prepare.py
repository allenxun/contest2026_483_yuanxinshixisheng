import pathlib,hashlib,json
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['work-in-progress/parallel-neon-probe-medium/audio-marker-v1/decode.py',
 'evidence/audio-route-20260910/k7sound-loopback-rxall-20260910-213805.bin']
items=[]
for n in names:
 b=(root/n).read_bytes();d=p/'input'/pathlib.Path(n).name;d.parent.mkdir(exist_ok=True)
 if d.exists():assert d.read_bytes()==b
 else:d.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
old=(p/'input/decode.py').read_text()
a=old.index('    text=data.decode(\'ascii\');words=[]')
b=old.index("    if len(words)!=256:",a)
new='''    # Normalize recognized serial TEXT terminators only, not PCM bytes.
    text=data.decode('ascii').replace('\\r\\r\\n','\\n').replace('\\r\\n','\\n')
    words=[]
    for line in text.split('\\n'):
        if not line.startswith('LOOP_PCM'):continue
        m=re.fullmatch(r'LOOP_PCM ([0-9a-f]+) ((?:[0-9a-f]{8} ){7}[0-9a-f]{8})',line)
        if not m:raise ValueError('malformed LOOP_PCM row')
        off,body=m.groups()
        if int(off,16)!=len(words):raise ValueError('noncontiguous or duplicate dump')
        words += [int(v,16) for v in body.split(' ')]
        if len(words)>256:raise ValueError('over 128 frames')
'''
(p/'decode.py').write_text(old[:a]+new+old[b:])
