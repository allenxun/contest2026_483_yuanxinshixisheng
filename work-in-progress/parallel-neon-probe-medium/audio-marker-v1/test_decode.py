import pathlib,json
from decode import encode,decode,parse,report
p=pathlib.Path(__file__).resolve().parent
for n in range(288):assert decode(encode(n))['enqueue_word']==n
assert decode(0)['kind']=='zero'
for bad in [1,0xffffffff,0x01000000,encode(0)|1,0x08081100]:assert decode(bad)['kind']=='invalid'
def log(words):
 return ('\n'.join('LOOP_PCM %04x '%i+' '.join('%08x'%w for w in words[i:i+8]) for i in range(0,256,8))+'\n').encode('ascii')
progress=[0]*8
for cycle in range(31):progress += [encode(8*cycle+6),encode(8*cycle+7)]+[0]*6
stale=[0]*8+([encode(6),encode(7)]+[0]*6)*31
rp,rs=report(log(progress)),report(log(stale))
assert rp['zero_words']==rs['zero_words']==194
assert rp['unique_enqueue_indices']==62 and rs['unique_enqueue_indices']==2
try:parse(log(progress)[:-20]);raise AssertionError('truncated accepted')
except ValueError:pass
try:parse(log(progress)+log(progress));raise AssertionError('duplicate accepted')
except ValueError:pass
old=[]
for name in ['k7sound-loopback-rxall-20260910-213805.bin','k7sound-loopback-20260910-213816.bin']:
 old.append(parse((p/'input/evidence/audio-route-20260910'/name).read_bytes())[1])
assert old[0]==old[1]==[0]*8+[0x0707ef00,0x08081100,0,0,0,0,0,0]*31
result=dict(all_288_roundtrips=True,zero_words_preserved=194,
 synthetic_progress_unique=62,synthetic_stale_unique=2,
 real_prior_rxall_equals_default=True,real_numbered_data_available=False)
(p/'decode-test-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
print('PASS decoder distinguishes synthetic progress/stale indices; rejects incomplete/duplicate input')
