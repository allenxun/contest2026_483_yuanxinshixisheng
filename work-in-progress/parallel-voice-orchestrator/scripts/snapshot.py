from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parents[1]
wip=root.parent
items={
 'include/voicelink/audio.hpp':wip/'parallel-voicelink-tuning/include/voicelink/audio.hpp',
 'src/audio.cpp':wip/'parallel-voicelink-tuning/src/audio.cpp',
 'include/wifi_broker.h':wip/'parallel-wifi-service/include/wifi_broker.h',
 'src/wifi_broker.c':wip/'parallel-wifi-service/src/wifi_broker.c',
 'vendor/sherpa-onnx/c-api/c-api.h':wip/'parallel-voicelink/vendor/sherpa-onnx/c-api/c-api.h',
 'vendor/LICENSE':wip/'parallel-voicelink/vendor/sherpa-onnx/LICENSE',
}
rows=[]
for dest,src in items.items():
 data=src.read_bytes()
 for p in [root/dest,root/'input'/dest]:
  p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(data)
 rows.append(dict(source=str(src),copy=dest,sha256=hashlib.sha256(data).hexdigest()))
for folder in ['parallel-voicelink','parallel-wifi-service','parallel-voicelink-runtime','parallel-voicelink-tuning']:
 for src in (wip/folder).glob('*.md'):
  rows.append(dict(source=str(src),sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
with (root/'input/sources.json').open('x',encoding='utf8') as f:json.dump(rows,f,ensure_ascii=False,indent=2)
