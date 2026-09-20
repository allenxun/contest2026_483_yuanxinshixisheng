import pathlib,re,json,hashlib,collections
R=pathlib.Path(__file__).resolve().parent;P=R.parents[2]
results=[];inputs=[]
for stamp in ['192042','192144']:
 p=P/('evidence/audio-mic-20260910/k7sound-dump-20260910-'+stamp+'.bin')
 data=p.read_bytes();(R/'input'/p.name).write_bytes(data)
 inputs.append({'source':str(p),'sha256':hashlib.sha256(data).hexdigest()})
 text=data.decode('ascii',errors='strict');lines=text.splitlines();words=[];headers=[];ends=0
 for line in lines:
  if line.startswith('SOUND_PCM frames='):
   m=re.fullmatch(r'SOUND_PCM frames=(\d+) rate=16000 channels=2 bits=32',line)
   if not m:raise ValueError('header')
   headers.append(int(m.group(1)))
  elif line.startswith('PCM '):
   m=re.fullmatch(r'PCM ([0-9a-f]{6})((?: [0-9a-f]{8}){1,8})',line)
   if not m:raise ValueError('row')
   if int(m.group(1),16)!=len(words):raise ValueError('offset discontinuity')
   words += [int(x,16) for x in m.group(2).split()]
  elif line=='SOUND_PCM_END':ends+=1
 if len(headers)!=1 or ends!=1 or len(words)!=headers[0]*2:raise ValueError('incomplete dump')
 frames=headers[0];channels=[]
 for ch in range(2):
  seq=words[ch::2];nz=[i for i,x in enumerate(seq) if x]
  phase0=seq[::4];lead=0
  for x in phase0:
   if x!=0xffffffff:break
   lead+=1
  bins=[]
  for phase in range(4):
   vals=seq[phase::4];c=collections.Counter(vals)
   bins.append({'phase_mod4':phase,'frames':len(vals),'nonzero':sum(x!=0 for x in vals),'unique':len(c),'common_hex':[(hex(k),v) for k,v in c.most_common(8)]})
  channels.append({'channel':ch,'nonzero':len(nz),'leading_phase0_ffffffff':lead,'non_sentinel_phase0_low8_nonzero':sum((x&255)!=0 for x in phase0 if x!=0xffffffff),'first_nonzero_indices':nz[:16],'last_nonzero_indices':nz[-8:],'nonzero_spacing':dict(collections.Counter(b-a for a,b in zip(nz,nz[1:]))),'phases':bins})
 result={'file':p.name,'validated_frames':frames,'validated_words':len(words),'offsets_contiguous':True,'header_end_unique':True,'channels':channels,'left_equals_right':all(words[i]==words[i+1] for i in range(0,len(words),2)),'word_values_hex':[(hex(k),v) for k,v in collections.Counter(words).most_common(12)]}
 results.append(result)
(R/'results.json').write_text(json.dumps(results,indent=2))
(R/'inputs.json').write_text(json.dumps(inputs,indent=2))
lines=['PASS dump structural validation: unique headers/end, contiguous hex offsets, exact word counts']
for r in results:
 lines.append('%s frames=%d nonzero=%s leading_phase0_ffffffff=%s phase1..3_zero=%s'%(r['file'],r['validated_frames'],[c['nonzero'] for c in r['channels']],[c['leading_phase0_ffffffff'] for c in r['channels']],all(all(b['nonzero']==0 for b in c['phases'][1:]) for c in r['channels'])))
(R/'analysis-output.txt').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
