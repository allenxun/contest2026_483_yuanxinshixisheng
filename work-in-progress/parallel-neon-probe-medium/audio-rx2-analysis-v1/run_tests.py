import pathlib,subprocess,json
p=pathlib.Path(__file__).resolve().parent;runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'rx2_ready.c','test.c','-o','test-'+opt+'.exe']
 c=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(c.stdout);assert c.returncode==0
 t=subprocess.run([str(p/('test-'+opt+'.exe'))],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
 (p/('test-'+opt+'.txt')).write_bytes(t.stdout);assert t.returncode==0
 runs.append(dict(command=cmd,compile_rc=c.returncode,test_rc=t.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS O0/O2 pure readiness predicate')
