import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
LOCK={
 'work-in-progress/parallel-robot-tools/include/dispatcher.hpp':'9cd03d888217c478a6ab78d31475a981a2ab27fa86cdc1ce3c71b309547b5564',
 'work-in-progress/parallel-robot-tools/HANDOFF.md':'4a4a1c36c91df3452520753b87b337f8f239b5b24a1347240d572bb8bb211e4b',
 'app/k7radio/cJSON.c':'cf9e08c8524c17406a0d430a47376080aebcdc8e851f7de24d277be61973eaeb',
 'app/k7radio/cJSON.h':'dd689a2905ad7c4c1d15556f1c7b9ce5cfdf9c8a78e4224ffb4a04d01d050f5f'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in LOCK.items():
 if sha(PROJECT/name)!=digest:raise SystemExit('input changed: '+name)
results=[]
for opt in ['-O0','-O2']:
 commands=[['g++','-std=c++17',opt,'-Wall','-Wextra','-Werror','-pedantic',
 '-I'+str(PROJECT/'work-in-progress/parallel-robot-tools/include'),
 'tool_json.cpp','test_tool_json.cpp','-o','tests'+opt+'.exe'],[str(ROOT/('tests'+opt+'.exe'))]]
 for command in commands:
  p=subprocess.run(command,cwd=str(ROOT),timeout=30,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  idx=len(results)
  (ROOT/(str(idx)+'.stdout')).write_bytes(p.stdout)
  (ROOT/(str(idx)+'.stderr')).write_bytes(p.stderr)
  results.append(dict(command=command,returncode=p.returncode,stdout=p.stdout.decode('utf-8','replace'),stderr=p.stderr.decode('utf-8','replace')))
  if p.returncode:break
 if results[-1]['returncode']:break
report=dict(scope='Actual C++17 parser plus frozen dispatcher header; no NuttX/model/backend',passed=len(results)==4 and all(r['returncode']==0 for r in results),results=results)
(ROOT/'host-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
manifest=dict(inputs=LOCK,outputs={p.name:sha(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='hashes.json'})
(ROOT/'hashes.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
