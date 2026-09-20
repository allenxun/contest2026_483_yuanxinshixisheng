import pathlib,hashlib,json,subprocess
ROOT=pathlib.Path(__file__).resolve().parent;PROJECT=ROOT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={};verification=[]
for folder in ['parallel-k7-audio','parallel-k7-codec']:
 base=PROJECT/'work-in-progress'/folder;m=base/'evidence/delivery.json';d=json.loads(m.read_text(encoding='utf-8'))
 results=[dict(path=name,match=sha(base/name)==digest) for name,digest in d['files'].items()]
 verification.append(dict(folder=folder,files=len(results),all_match=all(x['match'] for x in results),mismatches=[x for x in results if not x['match']]))
 if not verification[-1]['all_match']:raise SystemExit('frozen delivery changed')
 inputs[str(m.relative_to(PROJECT))]=sha(m)
for name in ['docs/VoiceLink交接接收与集成顺序_20260910.md','work-in-progress/parallel-k7-audio/HANDOFF.md','work-in-progress/parallel-k7-audio/HARDWARE.md','work-in-progress/parallel-k7-audio/PLAN.md','work-in-progress/parallel-k7-audio/audio_candidate.py','work-in-progress/parallel-k7-audio/sources/K7_V2.0_20250716_SCH-p35.txt','work-in-progress/parallel-k7-codec/HANDOFF.md','work-in-progress/parallel-k7-codec/include/codec_txn.h']:
 inputs[name]=sha(PROJECT/name)
photo=pathlib.Path('C:/Users/pc2025/AppData/Local/Temp/codex-clipboard-b6641dd4-1314-4a25-bff4-73465c8bb4ec.jpg');inputs[str(photo)]=sha(photo)
records=[]
for command in [['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','pcm_observer.c','test_pcm.c','-o','test_pcm.exe'],[str(ROOT/'test_pcm.exe')]]:
 p=subprocess.run(command,cwd=str(ROOT),timeout=15,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 i=len(records);(ROOT/(str(i)+'.stdout')).write_bytes(p.stdout);(ROOT/(str(i)+'.stderr')).write_bytes(p.stderr)
 records.append(dict(command=command,returncode=p.returncode,stdout=p.stdout.decode('utf-8','replace'),stderr=p.stderr.decode('utf-8','replace')))
 if p.returncode:break
(ROOT/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROOT/'delivery-verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
(ROOT/'host-results.json').write_text(json.dumps(dict(passed=len(records)==2 and all(r['returncode']==0 for r in records),scope='new PCM scalar analysis only; old tests not rerun; no hardware',records=records),indent=2)+'\n',encoding='utf-8')
(ROOT/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='hashes.json'},indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(deliveries=verification,tests=records),indent=2));raise SystemExit(0 if len(records)==2 and all(r['returncode']==0 for r in records) else 1)
