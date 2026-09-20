from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1];wip=R.parent;project=wip.parent
items={'include/wifi_broker.h':wip/'parallel-wifi-service/include/wifi_broker.h','src/wifi_broker.c':wip/'parallel-wifi-service/src/wifi_broker.c'}
rows=[]
for rel,p in items.items():
 data=p.read_bytes()
 for out in [R/rel,R/'input'/rel]:
  out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as f:f.write(data)
 rows.append(dict(source=str(p),copy=rel,sha256=hashlib.sha256(data).hexdigest()))
for prefix,names in [(project/'app/k7radio',['prov_wifi.inc','prov_service.inc','prov_protocol.h','prov_protocol.c','wifi_ip_service.inc','wifi_join_probe.inc','k7radio_main.c']),
 (wip/'parallel-wifi-service',['CONTRACT.md','HANDOFF.md','include/voicelink_adapter.hpp']),
 (wip/'parallel-voicelink',['include/voicelink/ports.hpp','include/voicelink/types.hpp','HANDOFF.md'])]:
 for name in names:
  p=prefix/name;data=p.read_bytes();out=R/'input'/prefix.name/name;out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as f:f.write(data)
  rows.append(dict(source=str(p),copy=str(out.relative_to(R)),sha256=hashlib.sha256(data).hexdigest()))
(R/'input/sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
print('snapshots',len(rows))
