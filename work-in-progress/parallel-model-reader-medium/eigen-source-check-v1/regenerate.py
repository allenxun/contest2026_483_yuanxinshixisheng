from pathlib import Path
import subprocess,hashlib,json
p=Path(__file__).parent.resolve();sha='e7248b26a1ed53fa030c5c459f7ea095dfd276ac';out=[]
for prefix,name in [('eigen-'+sha+'/','regenerated-commit.zip'),('eigen-3.4/','regenerated-3.4.zip')]:
 cmd=['git','-C',str(p/'git-proof'),'archive','--format=zip','--prefix='+prefix,sha]
 r=subprocess.run(cmd,capture_output=True,check=True,timeout=20);b=r.stdout;(p/name).write_bytes(b);out.append({'command':cmd,'file':name,'bytes':len(b),'sha1':hashlib.sha1(b).hexdigest(),'sha256':hashlib.sha256(b).hexdigest()})
(p/'regenerated.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
