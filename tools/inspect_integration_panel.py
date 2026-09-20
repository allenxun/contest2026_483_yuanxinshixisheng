from cloud_radio_stage_audit import remote,ROOT
import json,base64
d=json.loads(remote('''import pathlib,json,base64
p=pathlib.Path('/home/swl/openvela/work/velavision-project/evidence/integration-panel-20260916')
print(json.dumps({'log':(p/'window-console.log').read_text(),'image':base64.b64encode((p/'panel.png').read_bytes()).decode() if (p/'panel.png').exists() else None}))
'''))
print(d['log'])
if d['image']:(ROOT/'evidence/integration-panel-20260916/panel.png').write_bytes(base64.b64decode(d['image']))
