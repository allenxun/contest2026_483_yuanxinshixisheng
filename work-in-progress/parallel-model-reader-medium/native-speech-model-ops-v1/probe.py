from pathlib import Path
import json,hashlib,subprocess
p=Path(__file__).parent
old=p.parent/'native-voice-runtime-audit-v1/inputs.json'
records=json.loads(old.read_text(encoding='utf-8'));models=[]
for x in records:
 f=Path(x['path'])
 if f.suffix.lower()!='.onnx':continue
 h=hashlib.sha256()
 with f.open('rb') as src:
  for b in iter(lambda:src.read(1024*1024),b''):h.update(b)
 models.append({'path':str(f),'bytes':f.stat().st_size,'sha256':h.hexdigest(),'matches_prior':h.hexdigest()==x['sha256'],'opsets':None,'operators':None,'types':None,'external_data':None,'StringNormalizer':'UNKNOWN_NOT_PARSED'})
probe="import importlib.util; print('onnx',importlib.util.find_spec('onnx')); print('google',importlib.util.find_spec('google'))"
envs=[]
for exe in ['C:/Users/pc2025/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe','C:/Program Files/Python36/python.exe']:
 r=subprocess.run([exe,'-B','-c',probe],capture_output=True,timeout=15)
 envs.append({'python':exe,'exit':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')})
(p/'model-inputs.json').write_text(json.dumps(models,ensure_ascii=False,indent=2),encoding='utf-8');(p/'environment-probes.json').write_text(json.dumps(envs,indent=2));print(len(models),'models hashed; both environments lack onnx/protobuf')
