from pathlib import Path
import urllib.request,hashlib,json
p=Path(__file__).parent;(p/'sources').mkdir(exist_ok=True)
items=[('sherpa-root','k2-fsa/sherpa-onnx','26aa2fa93210376a89de3a65a1a4dd320c37f5e9','CMakeLists.txt'),('sherpa-ort','k2-fsa/sherpa-onnx','v1.12.14','cmake/onnxruntime.cmake'),('sherpa-csrc','k2-fsa/sherpa-onnx','v1.12.14','sherpa-onnx/csrc/CMakeLists.txt'),('ort-root','microsoft/onnxruntime','v1.17.1','cmake/CMakeLists.txt'),('ort-env','microsoft/onnxruntime','v1.17.1','onnxruntime/core/platform/posix/env.cc'),('ort-platform','microsoft/onnxruntime','v1.17.1','cmake/onnxruntime_common.cmake'),('ort-deps','microsoft/onnxruntime','v1.17.1','cmake/deps.txt')]
a=[]
for name,repo,ref,path in items:
 url=f'https://raw.githubusercontent.com/{repo}/{ref}/{path}'
 try:
  with urllib.request.urlopen(url,timeout=20) as resp:b=resp.read(300001)
  assert len(b)<=300000
  (p/'sources'/(name+'.txt')).write_bytes(b);a.append({'name':name,'url':url,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)})
 except Exception as e:a.append({'name':name,'url':url,'error':str(e)})
(p/'sources.json').write_text(json.dumps(a,indent=2));print(json.dumps(a,indent=2))
