from pathlib import Path
import hashlib,json,struct
r=Path('E:/openvela/VelaVision');p=r/'work-in-progress/parallel-model-reader-medium/native-voice-runtime-audit-v1'
base=Path('E:/openvela/语音模块/openvela-voicelink/models')
files=[base/'sherpa-onnx-streaming-paraformer-bilingual-zh-en'/n for n in ['encoder.int8.onnx','decoder.int8.onnx','tokens.txt','test_wavs/0.wav']]
files += [base/'vits-icefall-zh-aishell3'/n for n in ['model.onnx','tokens.txt','lexicon.txt','rule.far']]
lib=r/'work-in-progress/parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib'
files += [lib/n for n in ['sherpa-onnx-c-api.dll','onnxruntime.dll']]
small=['app/voicelink/README.md','app/voicelink/include/voicelink/ports.hpp','app/k7agent/model_reader/model_reader.h','port/new/nuttx/include/nuttx/mm/k7_model_arena.h','app/k7fat/k7fat_main.c','work-in-progress/parallel-voicelink-runtime/HANDOFF.md','work-in-progress/parallel-voicelink-runtime/MODELS.md','work-in-progress/parallel-voicelink/vendor/sherpa-onnx/version-lock.json','work-in-progress/parallel-voicelink/vendor/sherpa-onnx/c-api/c-api.h','work-in-progress/parallel-voicelink/src/audio.cpp','work-in-progress/parallel-voicelink-tuning/input/sherpa-onnx/csrc/online-recognizer-paraformer-impl.h']
files += [r/n for n in small]
a=[]
for f in files:
 h=hashlib.sha256()
 with f.open('rb') as stream:
  while b:=stream.read(1024*1024):h.update(b)
 v={'path':str(f),'bytes':f.stat().st_size,'sha256':h.hexdigest(),'verification':'streamed actual local bytes; no execution'}
 if f.suffix=='.dll':
  with f.open('rb') as st:
   head=st.read(64);st.seek(struct.unpack_from('<I',head,60)[0]);pe=st.read(6)
  v['PE_machine']=hex(struct.unpack_from('<H',pe,4)[0]);v['platform']='Windows PE AMD64, not NuttX'
 a.append(v)
(p/'inputs.json').write_text(json.dumps(a,indent=2))
(p/'inventory.txt').write_text('\n'.join(f"{x['bytes']} {x['sha256']} {x['path']}" for x in a))
print('Hashed',len(a),'files;',sum(x['bytes'] for x in a),'bytes; DLL PE types:',[x.get('PE_machine') for x in a if 'PE_machine' in x])
