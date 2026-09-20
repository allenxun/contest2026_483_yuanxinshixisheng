from pathlib import Path
import json,subprocess,hashlib
R=Path(__file__).resolve().parents[1]
source=Path(r'E:\openvela\无线适配_2026-09-08\official-linux-20260320')
tree=json.loads((source/'tree.json').read_text(encoding='utf8'))
paths=['kernel-6.1/arch/arm64/boot/dts/rockchip/'+n for n in ['rk3576-kickpi-k7-linux.dts','rk3576-kickpi-k7.dtsi','rk3576-kickpi-evb.dtsi','rk3576.dtsi','rk3576-pinctrl.dtsi']]
paths+=['kernel-6.1/sound/soc/codecs/'+n for n in ['es8388.c','es8388.h','es8323.c','es8323.h','es8328.c','es8328.h']]
paths+=['kernel-6.1/sound/soc/rockchip/'+n for n in ['rockchip_i2s_tdm.c','rockchip_i2s_tdm.h','rockchip_multicodecs.c','rockchip_sai.c','rockchip_sai.h']]
rows=[]
for path in paths:
 hit=next((x for x in tree if x['path']==path),None)
 if not hit:print('not present',path);continue
 data=subprocess.check_output(['git','--git-dir='+str(source/'object-store'),'cat-file','blob',hit['oid']],timeout=30)
 assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==hit['oid']
 out=R/'sources'/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
 rows.append(dict(path=path,oid=hit['oid'],bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
(R/'evidence/linux-inputs.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
print('selected blobs',len(rows),'bytes',sum(x['bytes'] for x in rows))
