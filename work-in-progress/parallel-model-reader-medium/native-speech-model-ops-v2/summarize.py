from pathlib import Path
import json,collections,hashlib
p=Path(__file__).parent;union=collections.defaultdict(set);details=[]
for name in ['encoder','decoder','vits']:
 r=json.loads((p/(name+'.json')).read_text(encoding='utf-8'));local=collections.defaultdict(set)
 for op in r['operators']:
  assert op['opset'] is not None
  domain=op['domain'] or 'ai.onnx';local[(domain,op['opset'])].add(op['operator']);union[(domain,op['opset'])].add(op['operator'])
 lines=[f'{d};{v};'+','.join(sorted(ops)) for (d,v),ops in sorted(local.items())]
 (p/(name+'-required.config')).write_text('\n'.join(lines)+'\n')
 declared={v['name']:v['type'] for g in r['graphs'] for kind in ['inputs','outputs','value_info'] for v in g[kind]}
 known=set(declared)|{t['name'] for t in r['tensors'] if '/initializer' in t['scope']}
 outputs={o for n in r['nodes'] for o in n['outputs'] if o}
 details.append({'model':name,'used_domains':sorted({op['domain'] for op in r['operators']}),'required_lines':lines,'declared_value_types':declared,'unannotated_node_output_count':len(outputs-known)})
(p/'speech-required.config').write_text('\n'.join(f'{d};{v};'+','.join(sorted(ops)) for (d,v),ops in sorted(union.items()))+'\n')
(p/'operator-type-summary.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8');print((p/'speech-required.config').read_text())
root=p.parents[2];inst=root/'evidence/native-model-parser-install-20260911.json';(p/'parser-input.json').write_text(json.dumps({'install_report':str(inst),'sha256':hashlib.sha256(inst.read_bytes()).hexdigest()},indent=2))
