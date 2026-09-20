import pathlib,subprocess,hashlib,json
p=pathlib.Path(__file__).resolve().parent
root=p.parents[3]
sources=['app/k7sound/pio.c','app/k7sound/pio.h','app/k7sound/input/rockchip_sai.h']
items=[]
for name in sources:
 data=(root/name).read_bytes()
 dest=p/'input'/pathlib.Path(name).name
 dest.parent.mkdir(exist_ok=True)
 if dest.exists():assert dest.read_bytes()==data,'Frozen source changed'
 else:dest.write_bytes(data)
 items.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest()))
(p/'inputs.json').write_text(json.dumps(items,indent=2))
runs=[]
for opt in ('O0','O2'):
 cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-'+opt,'duplex.c','test.c','-o','test-'+opt+'.exe']
 c=subprocess.run(cmd,cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('compile-'+opt+'.txt')).write_bytes(c.stdout)
 assert c.returncode==0,c.stdout
 t=subprocess.run([str(p/('test-'+opt+'.exe'))],cwd=str(p),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
 (p/('test-'+opt+'.txt')).write_bytes(t.stdout)
 assert t.returncode==0,t.stdout
 runs.append(dict(command=cmd,compile_rc=c.returncode,test_rc=t.returncode))
(p/'runs.json').write_text(json.dumps(runs,indent=2))
print('PASS strict O0/O2 duplex runner simulation')
