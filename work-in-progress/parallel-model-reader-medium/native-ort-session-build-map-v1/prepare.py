from pathlib import Path
import json,hashlib
p=Path(__file__).parent;root=p.parents[2];ort=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d'
names=['cmake/CMakeLists.txt','cmake/onnxruntime.cmake','cmake/onnxruntime_session.cmake','cmake/onnxruntime_framework.cmake','cmake/onnxruntime_graph.cmake','cmake/onnxruntime_optimizer.cmake','cmake/onnxruntime_providers.cmake','cmake/onnxruntime_providers_cpu.cmake','cmake/onnxruntime_flatbuffers.cmake','cmake/onnxruntime_mlas.cmake','cmake/onnxruntime_util.cmake','cmake/external/onnxruntime_external_deps.cmake','cmake/external/protobuf_function.cmake','cmake/deps.txt','tools/ci_build/reduce_op_kernels.py']
inputs={}
for n in names:
 f=ort/n;inputs[str(f)]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
locks=[]
for line in (ort/'cmake/deps.txt').read_text().splitlines():
 if line and not line.startswith('#'):
  cols=line.split(';')
  if cols[0] in ['onnx','protobuf','flatbuffers','mp11','re2','json','safeint','microsoft_gsl','eigen','abseil_cpp','google_nsync','date','pytorch_cpuinfo']:
   locks.append({'name':cols[0],'url':cols[1],'sha1':cols[2],'local_archive_present':(ort.parent/'deps'/(cols[0]+'.zip')).exists()})
(p/'dependency-lock-map.json').write_text(json.dumps(locks,indent=2))
