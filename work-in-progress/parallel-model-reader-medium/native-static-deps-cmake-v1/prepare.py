from pathlib import Path
import hashlib,json,re
p=Path(__file__).parent;root=p.parents[2];ort=root/'work-in-progress/native-voice-sources/onnxruntime-8f5c79cb63f09ef1302e85081093a3fe4da1bc7d';stage=root/'private/native-ort-env-stage'
f=ort/'cmake/external/abseil-cpp.cmake';text=f.read_text();block=text[text.index('set(ABSEIL_LIBS'):];names=re.findall(r'absl::\w+',block)
assert len(names)==21
(p/'ort-abseil-targets.cmake').write_text('# Exact ORT 1.17.1 ABSEIL_LIBS roots; upstream resolves transitive dependencies.\nset(K7_ORT_ABSEIL_LIBS\n  '+'\n  '.join(names)+'\n)\n')
files=[f,stage/'abseil_cpp/CMakeLists.txt',stage/'google_nsync/CMakeLists.txt',stage/'google_nsync/VERSION',p.parent/'common-closure-v1/abseil-declared-closure.json']
inputs={str(f):{'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in files};(p/'inputs.json').write_text(json.dumps(inputs,indent=2));print('21 exact root targets extracted; no configure/build attempted')
