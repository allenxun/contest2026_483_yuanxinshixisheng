import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((ROOT/'inputs.json').read_text(encoding='utf-8'))
for name,digest in inputs.items():
 if sha(PROJECT/name)!=digest:raise SystemExit('input changed: '+name)
results=[]
for source,name in [(str(PROJECT/'tests/wifi/test_amsdu.c'),'original'),('replay_synthetic.c','synthetic')]:
 for command in [['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(PROJECT/'app/k7radio'),source,'-o',name+'.exe'],[str(ROOT/(name+'.exe'))]]:
  p=subprocess.run(command,cwd=str(ROOT),timeout=15,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  idx=len(results);(ROOT/(str(idx)+'.stdout')).write_bytes(p.stdout);(ROOT/(str(idx)+'.stderr')).write_bytes(p.stderr)
  results.append(dict(command=command,returncode=p.returncode,stdout=p.stdout.decode('utf-8','replace'),stderr=p.stderr.decode('utf-8','replace')))
  if p.returncode:break
 if results[-1]['returncode']:break
report=dict(scope='Actual parser header host tests; synthetic frames, not captured frames',passed=len(results)==4 and all(r['returncode']==0 for r in results),results=results)
(ROOT/'host-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(ROOT/'hashes.json').write_text(json.dumps({p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='hashes.json'},indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
