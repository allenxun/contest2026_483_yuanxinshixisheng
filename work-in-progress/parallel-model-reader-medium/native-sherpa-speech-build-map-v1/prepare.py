from pathlib import Path
import re,json,hashlib
p=Path(__file__).parent;root=p.parents[2];s=root/'work-in-progress/native-voice-sources/sherpa-onnx-26aa2fa93210376a89de3a65a1a4dd320c37f5e9'
recipes=['kaldi-native-fbank','kaldi-decoder','kaldifst','openfst','simple-sentencepiece','cppjieba','cppinyin','espeak-ng-for-piper','piper-phonemize'];inputs={};locks=[]
for n in recipes:
 f=s/'cmake'/(n+'.cmake');b=f.read_bytes();t=b.decode();inputs[str(f)]=hashlib.sha256(b).hexdigest();locks.append({'recipe':n,'path':str(f),'source_settings':[{'line':i,'text':l.strip()} for i,l in enumerate(t.splitlines(),1) if re.search(r'set\(.*(URL|HASH)|FetchContent_Declare|PATCH_COMMAND|include\(|add_subdirectory',l)]})
for n in ['CMakeLists.txt','sherpa-onnx/csrc/CMakeLists.txt','sherpa-onnx/c-api/CMakeLists.txt','cmake/onnxruntime.cmake','sherpa-onnx/csrc/online-recognizer-paraformer-impl.h','sherpa-onnx/csrc/online-paraformer-model.cc','sherpa-onnx/csrc/features.cc','sherpa-onnx/csrc/offline-tts-vits-impl.h','sherpa-onnx/csrc/offline-tts-vits-model.cc']:
 f=s/n;inputs[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
(p/'dependency-recipes.json').write_text(json.dumps(locks,indent=2));(p/'inputs.json').write_text(json.dumps(inputs,indent=2))
print('\n'.join(n['recipe']+': '+str([v['text'] for v in n['source_settings'] if 'HASH' in v['text']]) for n in locks))
