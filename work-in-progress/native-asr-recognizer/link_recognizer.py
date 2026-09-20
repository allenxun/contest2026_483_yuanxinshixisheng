import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent;out=r/'link2';out.mkdir()
base=json.loads((r/'compile-attempt2.json').read_text())['command']
commands=[]
for source in ['online-paraformer-model-config.cc','recognizer_probe.cpp','sha256_vendor.c']:
 cmd=base[:];cmd[cmd.index('-c')+1]=str(r/source);cmd[cmd.index('-o')+1]=str(out/(source+'.o'))
 if source.endswith('.c'):
  cmd=[x for x in cmd if not x.startswith('-std=') and x!='-nostdinc++'];cmd[0]=cmd[0].replace('-g++','-gcc');cmd+=['-I'+str(r/'vendor')]
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);(out/(source+'.log')).write_bytes(p.stdout);commands.append(cmd)
 if p.returncode:raise RuntimeError(source+' compile failed; inspect saved log')
prior=json.loads((r.parent/'native-vits-lexicon-20260911/link1/result.json').read_text())
compiler=base[0];ar=compiler.replace('-g++','-ar');ld=compiler.replace('-g++','-ld')
archives=[Path(x['path']) for x in prior['inputs'] if x['path'].endswith('.a')]
for item in prior['inputs']:
 if item['path'].endswith('.a'):assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
replaced=[]
for i,path in enumerate(archives):
 members=subprocess.check_output([ar,'t',str(path)],text=True).splitlines()
 matches=[x for x in ['online-paraformer-model.cc.obj','online-paraformer-model-config.cc.obj'] if x in members]
 if not matches:continue
 dst=out/path.name;assert not dst.exists();shutil.copyfile(path,dst)
 for member in matches:
  src=r/'online-paraformer-model.cc.o' if member=='online-paraformer-model.cc.obj' else out/'online-paraformer-model-config.cc.o'
  assert src.exists();replacement=out/member;shutil.copyfile(src,replacement)
  subprocess.run([ar,'r',str(dst),str(replacement)],check=True)
  replaced.append({'archive':str(path),'member':member,'replacement_sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
 archives[i]=dst
assert len(replaced)==2
probe=Path(prior['inputs'][0]['path']);assert probe.name=='add_probe.o'
cmd=[ld,'-r','--undefined=SherpaOnnxCreateOnlineRecognizer','--undefined=SherpaOnnxCreateOfflineTts','--strip-debug','-o',str(out/'recognizer-runtime.o'),str(probe),str(out/'recognizer_probe.cpp.o'),str(out/'sha256_vendor.c.o'),'--start-group',*[str(x) for x in archives],'--end-group']
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);(out/'link.log').write_bytes(p.stdout)
result={'exit_code':p.returncode,'commands':commands,'link_command':cmd,'replaced':replaced,'board_tested':False,'firmware_linked':False}
if p.returncode==0:result['runtime_sha256']=hashlib.sha256((out/'recognizer-runtime.o').read_bytes()).hexdigest()
(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('commands','link_command','replaced')}))
