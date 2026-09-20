import pathlib,subprocess,json,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
PROJECT=ROOT.parents[3]
subprocess.run(['python',str(ROOT/'generate.py')],check=True,timeout=15)
# Separate translation unit compiles frozen baseline, not diagnostic header.
baseline='''#include "%s"
int baseline(struct skw_amsdu_rx*a,struct skw_data_replay*r,const uint8_t*p,uint64_t time,int(*deliver)(const uint8_t*,size_t)) {
 static const uint8_t own[6]={2,0,0,0,0,1};
 return skw_amsdu_receive(a,r,p,120,0,0,own,time,deliver);
}
''' % (PROJECT/'app/k7radio/skw_wifi_amsdu.h').as_posix()
(ROOT/'baseline.c').write_text(baseline,encoding='utf-8')
results=[]
sets=[([str(PROJECT/'tests/wifi/test_amsdu.c')],'original-on-candidate'),(['test_diag.c','baseline.c'],'differential')]
for sources,name in sets:
 commands=[['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT),'-I'+str(PROJECT/'app/k7radio')]+sources+['-o',name+'.exe'],[str(ROOT/(name+'.exe'))]]
 for command in commands:
  p=subprocess.run(command,cwd=str(ROOT),timeout=15,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  i=len(results);(ROOT/(str(i)+'.stdout')).write_bytes(p.stdout);(ROOT/(str(i)+'.stderr')).write_bytes(p.stderr)
  results.append(dict(command=command,returncode=p.returncode,stdout=p.stdout.decode('utf-8','replace'),stderr=p.stderr.decode('utf-8','replace')))
  if p.returncode:break
 if results[-1]['returncode']:break
report=dict(scope='Host actual candidate vs frozen baseline, no SDK/device/service integration build',passed=len(results)==4 and all(r['returncode']==0 for r in results),results=results)
(ROOT/'host-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(ROOT/'hashes.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='hashes.json'},indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
