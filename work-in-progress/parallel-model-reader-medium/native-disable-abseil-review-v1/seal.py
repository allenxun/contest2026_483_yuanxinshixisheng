from pathlib import Path
import hashlib,json
p=Path(__file__).parent;root=p.parents[2];ort=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';ab=root/'private/native-ort-env-stage/abseil_cpp'
ns=['cmake/CMakeLists.txt','cmake/onnxruntime_common.cmake','cmake/onnxruntime_framework.cmake','cmake/external/onnxruntime_external_deps.cmake','cmake/external/abseil-cpp.cmake','include/onnxruntime/core/common/inlined_containers.h','include/onnxruntime/core/common/inlined_containers_fwd.h','include/onnxruntime/core/platform/ort_mutex.h','onnxruntime/core/providers/cpu/ml/label_encoder.h']
fs=[ort/n for n in ns]+[ab/'absl/synchronization/mutex.cc',ab/'absl/synchronization/internal/create_thread_identity.cc']
(p/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in fs},indent=2))
outs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.iterdir() if f.is_file() and f.name not in ('outputs.json','delivery.json')};(p/'outputs.json').write_text(json.dumps(outs,indent=2));d={'status':'READ_ONLY_PARTIAL_ALTERNATIVE_NOT_ALLOCATOR_CLOSURE','outputs_sha256':hashlib.sha256((p/'outputs.json').read_bytes()).hexdigest()};(p/'delivery.json').write_text(json.dumps(d,indent=2));print(d);print(hashlib.sha256((p/'delivery.json').read_bytes()).hexdigest())
