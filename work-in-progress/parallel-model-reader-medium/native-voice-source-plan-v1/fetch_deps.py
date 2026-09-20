from pathlib import Path
import urllib.request,json,hashlib
p=Path(__file__).parent;a=json.loads((p/'sources.json').read_text())
urls=[('ort-tag','https://api.github.com/repos/microsoft/onnxruntime/git/ref/tags/v1.17.1')]+[(n,'https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/26aa2fa93210376a89de3a65a1a4dd320c37f5e9/'+path) for n,path in [('sherpa-capi','sherpa-onnx/c-api/CMakeLists.txt'),('dep-fbank','cmake/kaldi-native-fbank.cmake'),('dep-decoder','cmake/kaldi-decoder.cmake'),('dep-fst','cmake/kaldifst.cmake'),('dep-sentencepiece','cmake/simple-sentencepiece.cmake'),('dep-jieba','cmake/cppjieba.cmake'),('dep-pinyin','cmake/cppinyin.cmake'),('dep-piper','cmake/piper-phonemize.cmake'),('dep-espeak','cmake/espeak-ng-for-piper.cmake')]]
for n,url in urls:
 try:
  with urllib.request.urlopen(url,timeout=15) as f:b=f.read(150001)
  assert len(b)<=150000
  (p/'sources'/(n+'.txt')).write_bytes(b);a.append({'name':n,'url':url,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
 except Exception as e:a.append({'name':n,'url':url,'error':str(e)})
(p/'sources.json').write_text(json.dumps(a,indent=2));print([(x['name'],x.get('error','ok')) for x in a]);print((p/'sources/ort-tag.txt').read_text())
