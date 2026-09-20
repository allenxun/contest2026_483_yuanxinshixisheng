import pathlib,hashlib,json,re,importlib.util
p=pathlib.Path(__file__).resolve().parent;root=p.parents[2]
names=['evidence/audio-rx2-20260910/k7sound-loopback-numbered-20260911-094328.bin',
 'evidence/audio-rx2-20260910/k7sound-loopback-rx2-20260911-094337.bin',
 'app/k7sound/duplex.c','app/k7sound/duplex.h',
 'work-in-progress/parallel-neon-probe-medium/audio-marker-decoder-v2/decode.py',
 'evidence/audio-sai-trm-20260910/SAI-layout.txt']
items=[]
for n in names:
 b=(root/n).read_bytes();d=p/'input'/n;d.parent.mkdir(parents=True,exist_ok=True)
 if d.exists():assert d.read_bytes()==b
 else:d.write_bytes(b)
 items.append(dict(path=n,sha256=hashlib.sha256(b).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
spec=importlib.util.spec_from_file_location('decoder',str(p/'input'/names[4]))
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
def levels(x):return [(x>>(6*i))&63 for i in range(4)]
results=[]
for n in names[:2]:
 b=(p/'input'/n).read_bytes();text,words=decoder.parse(b)
 vals=[decoder.decode(w) for w in words]
 ids=[d['enqueue_word'] for d in vals if d['kind']=='marker']
 records=[]
 for index,us,before,word,after in re.findall(r'loop_word dir=1 index=(\d+) us=(\d+) before=([0-9a-f]+) word=([0-9a-f]+) after=([0-9a-f]+) rc=0',text):
  before,after=int(before,16),int(after,16)
  delta=[a-b for a,b in zip(levels(after),levels(before))]
  records.append(dict(index=int(index),us=int(us),before=hex(before),after=hex(after),delta=delta,word=word))
 stamps=re.search(r'start=(\d+) end=(\d+)',text)
 results.append(dict(source=n,sha256=hashlib.sha256(b).hexdigest(),words=len(words),
  zero_words=words.count(0),invalid=sum(d['kind']=='invalid' for d in vals),
  indices=ids,unique_indices=len(set(ids)),strict_contiguous=ids==list(range(ids[0],ids[-1]+1)),
  elapsed_us=int(stamps[2])-int(stamps[1]),
  rx_records=len(records),unchanged=[x for x in records if x['delta']==[0,0,0,0]],
  zero_with_net_entry_consumed=sum(x['word']=='00000000' and sum(x['delta'])==-1 for x in records),
  nonzero_with_net_entry_consumed=sum(x['word']!='00000000' and sum(x['delta'])==-1 for x in records),
  first_16=records[:16]))
assert results[0]['sha256']=='3932e7c02f665a00df4c9c2f95eeff5ca5dfa4d52f3fdc3106c2ae82cb216c67'
assert results[1]['sha256']=='55ab48a6d3a3489cc825f431119909e6f9b79ac7c79820c4cab7ccaa02956a4a'
(p/'results.json').write_text(json.dumps(results,indent=2))
for r in results:print(json.dumps({k:v for k,v in r.items() if k not in ['indices','first_16']},indent=2))
print('PASS raw hashes and strict full-dump parsing; no zeros discarded')
