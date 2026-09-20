"""Offline numbered-loopback decoder. Prints JSON; never rewrites audio."""
import json,re,sys,pathlib
def encode(n):
    if not 0<=n<288:raise ValueError('enqueue word index outside 0..287')
    return 0x01000000|((n&7)<<20)|(((n>>3)+1)<<8)
def decode(w):
    if w==0:return dict(kind='zero')
    if (w&0xff8000ff)!=0x01000000:return dict(kind='invalid',raw='%08x'%w)
    cycle=((w>>8)&4095)-1
    n=cycle*8+((w>>20)&7)
    if cycle<0 or not 0<=n<288 or encode(n)!=w:return dict(kind='invalid',raw='%08x'%w)
    return dict(kind='marker',enqueue_word=n,cycle=cycle,position=n%8)
def parse(data):
    if len(data)>2*1024*1024:raise ValueError('log exceeds 2MiB bound')
    # Normalize recognized serial TEXT terminators only, not PCM bytes.
    text=data.decode('ascii').replace('\r\r\n','\n').replace('\r\n','\n')
    words=[]
    for line in text.split('\n'):
        if not line.startswith('LOOP_PCM'):continue
        m=re.fullmatch(r'LOOP_PCM ([0-9a-f]+) ((?:[0-9a-f]{8} ){7}[0-9a-f]{8})',line)
        if not m:raise ValueError('malformed LOOP_PCM row')
        off,body=m.groups()
        if int(off,16)!=len(words):raise ValueError('noncontiguous or duplicate dump')
        words += [int(v,16) for v in body.split(' ')]
        if len(words)>256:raise ValueError('over 128 frames')
    if len(words)!=256:raise ValueError('128-frame complete raw dump required')
    return text,words
def report(data):
    text,words=parse(data);rows=[];bad=0;zero=0;indices=[]
    queued=re.findall(r'loopback result=-?\d+ frames=128 tx_queued=(\d+)',text)
    limit=int(queued[0]) if len(queued)==1 else None
    for i,w in enumerate(words):
        d=decode(w);d.update(rx_word=i,rx_frame=i//2,channel=i%2,raw='%08x'%w)
        if d['kind']=='marker':
            d['rx_word_minus_enqueue_word']=i-d['enqueue_word']
            d['within_reported_enqueue_count']=None if limit is None else d['enqueue_word']<limit
            indices.append(d['enqueue_word'])
        elif d['kind']=='zero':zero+=1
        else:bad+=1
        rows.append(d)
    tx=[]
    for n,w in re.findall(r'loop_word dir=0 index=(\d+) .*?word=([0-9a-f]+) .*?rc=0',text):
        n=int(n);tx.append(dict(index=n,raw=w,matches_encoder=0<=n<288 and encode(n)==int(w,16)))
    return dict(frames=128,zero_words=zero,invalid_nonzero_words=bad,
       unique_enqueue_indices=len(set(indices)),reported_tx_queued=limit,
       tx_trace=tx,rx=rows,
       interpretation='Indices describe enqueued source words only; lag is not proven physical latency. Zeros preserved.')
if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('usage: python decode.py raw-log.bin')
    print(json.dumps(report(pathlib.Path(sys.argv[1]).read_bytes()),indent=2))
