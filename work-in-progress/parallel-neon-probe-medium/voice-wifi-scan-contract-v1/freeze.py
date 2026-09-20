import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
P=R.parents[2]
paths=[]
for name in ['parallel-wifi-dispatch','parallel-wifi-service']:
 b=P/'work-in-progress'/name
 paths += [b/n for n in ['HANDOFF.md','CONTRACT.md','INTEGRATION.md']]
 paths += list((b/'include').glob('*'))+list((b/'src').glob('*'))
paths += [P/'app/k7radio'/n for n in ['k7radio_main.c','prov_service.inc','prov_wifi.inc','prov_protocol.h','prov_protocol.c','wifi_assoc_probe.inc','wifi_ip_service.inc','wifi_auth_console.inc']]
paths += list((P/'work-in-progress/parallel-voicelink/include/voicelink').glob('*.hpp'))
records=[]
for i,p in enumerate(paths):
 if not p.is_file(): continue
 data=p.read_bytes(); dest=R/'input'/('%02d_'%i+p.name);dest.write_bytes(data)
 records.append({'source':str(p.relative_to(P)),'snapshot':dest.name,'sha256':hashlib.sha256(data).hexdigest()})
(R/'inputs.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
hashes={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.name!='outputs.json'}
(R/'outputs.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print('Frozen %d source inputs; interface proposal only, no runtime tests'%len(records))
