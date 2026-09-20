from pathlib import Path
import json,hashlib
from pypdf import PdfReader
R=Path(__file__).resolve().parents[1]
base=Path(r'E:\rk3576_data\4-HardwareData\K7')
rows=[]
for name in ['K7_V2.0_20250716_SCH.pdf','K7_V1.1_20241211_SCH.pdf']:
 p=base/name;reader=PdfReader(p);rows.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pages':len(reader.pages)})
 for i,page in enumerate(reader.pages,1):
  text=page.extract_text() or ''
  (R/'sources'/f'{p.stem}-p{i:02}.txt').write_text(text,encoding='utf8')
  if any(w in text.lower() for w in ['codec','es8388','es8389','speaker','audio','micbias','i2s']):print(name,i,text[:100].replace('\n',' '))
(R/'evidence/pdf-inputs.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
src=Path(r'E:\openvela\无线适配_2026-09-08\official-linux-20260320')
tree=json.loads((src/'tree.json').read_text(encoding='utf8'))
selected=[r for r in tree if ('rk3576' in r['path'].lower() and r['path'].endswith(('.dts','.dtsi'))) or ('sound/soc/codecs/' in r['path'] and any(x in r['path'] for x in ['es83','rk817']))]
(R/'sources/audio-paths.json').write_text(json.dumps(selected,indent=2),encoding='utf8')
for r in selected:print(r['path'])
