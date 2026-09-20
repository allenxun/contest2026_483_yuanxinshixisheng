from pathlib import Path
import sys,json,hashlib,collections
sys.path.insert(0,'E:/openvela/VelaVision/work-in-progress/native-model-parser-python')
import onnx
import google.protobuf
p=Path(__file__).parent
prior=json.loads((p.parent/'native-speech-model-ops-v1/model-inputs.json').read_text(encoding='utf-8'))
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as s:
  for b in iter(lambda:s.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def typ(t):
 if t.HasField('tensor_type'):
  q=t.tensor_type;return {'kind':'tensor','dtype':onnx.TensorProto.DataType.Name(q.elem_type),'shape':[d.dim_value if d.HasField('dim_value') else d.dim_param if d.HasField('dim_param') else None for d in q.shape.dim] if q.HasField('shape') else None}
 if t.HasField('sequence_type'):return {'kind':'sequence','element':typ(t.sequence_type.elem_type)}
 if t.HasField('optional_type'):return {'kind':'optional','element':typ(t.optional_type.elem_type)}
 if t.HasField('map_type'):return {'kind':'map','key':onnx.TensorProto.DataType.Name(t.map_type.key_type),'value':typ(t.map_type.value_type)}
 if t.HasField('sparse_tensor_type'):return {'kind':'sparse_tensor','dtype':onnx.TensorProto.DataType.Name(t.sparse_tensor_type.elem_type)}
 return {'kind':'unknown','protobuf_fields':[f.name for f,v in t.ListFields()]}
all_reports=[]
for entry in prior:
 f=Path(entry['path']);before=sha(f);m=onnx.load_model(str(f),load_external_data=False)
 nodes=[];graphs=[];tensors=[];functions=[]
 def tensor(t,where):
  tensors.append({'scope':where,'name':t.name,'dtype':onnx.TensorProto.DataType.Name(t.data_type),'dims':list(t.dims),'data_location':onnx.TensorProto.DataLocation.Name(t.data_location),'external_data':[{'key':e.key,'value':e.value} for e in t.external_data]})
 def visit_nodes(ns,scope,imports):
  for i,n in enumerate(ns):
   loc=f'{scope}/node[{i}]';domain=n.domain
   nodes.append({'scope':loc,'name':n.name,'domain':domain,'operator':n.op_type,'imported_opset':imports.get(domain),'inputs':list(n.input),'outputs':list(n.output)})
   for a in n.attribute:
    aloc=loc+'/attribute:'+a.name
    if a.type==onnx.AttributeProto.GRAPH:graph(a.g,aloc,imports)
    elif a.type==onnx.AttributeProto.GRAPHS:
     for j,g in enumerate(a.graphs):graph(g,aloc+f'[{j}]',imports)
    elif a.type==onnx.AttributeProto.TENSOR:tensor(a.t,aloc)
    elif a.type==onnx.AttributeProto.TENSORS:
     for j,t in enumerate(a.tensors):tensor(t,aloc+f'[{j}]')
    elif a.type==onnx.AttributeProto.SPARSE_TENSOR:
     tensor(a.sparse_tensor.values,aloc+'/values');tensor(a.sparse_tensor.indices,aloc+'/indices')
    elif a.type==onnx.AttributeProto.SPARSE_TENSORS:
     for j,t in enumerate(a.sparse_tensors):tensor(t.values,aloc+f'[{j}]/values');tensor(t.indices,aloc+f'[{j}]/indices')
 def graph(g,scope,imports):
  graphs.append({'scope':scope,'name':g.name,'inputs':[{'name':v.name,'type':typ(v.type)} for v in g.input],'outputs':[{'name':v.name,'type':typ(v.type)} for v in g.output],'value_info':[{'name':v.name,'type':typ(v.type)} for v in g.value_info]})
  for t in g.initializer:tensor(t,scope+'/initializer')
  for t in g.sparse_initializer:tensor(t.values,scope+'/sparse_initializer/values');tensor(t.indices,scope+'/sparse_initializer/indices')
  visit_nodes(g.node,scope,imports)
 imports={x.domain:x.version for x in m.opset_import};graph(m.graph,'graph',imports)
 for i,fn in enumerate(m.functions):
  imp={x.domain:x.version for x in fn.opset_import};scope=f'function[{i}]/{fn.domain}:{fn.name}'
  functions.append({'scope':scope,'domain':fn.domain,'name':fn.name,'opsets':imp,'inputs':list(fn.input),'outputs':list(fn.output)})
  visit_nodes(fn.node,scope,imp)
 counts=collections.Counter((n['domain'],n['imported_opset'],n['operator']) for n in nodes)
 report={'path':str(f),'bytes':f.stat().st_size,'sha256_before':before,'sha256_after':sha(f),'matches_prior':before==entry['sha256'],'training_info_count':len(m.training_info),'ir_version':m.ir_version,'opsets':imports,'graphs':graphs,'functions':functions,'operators':[{'domain':k[0],'opset':k[1],'operator':k[2],'nodes':v} for k,v in sorted(counts.items(),key=lambda kv:str(kv[0]))],'nodes':nodes,'tensors':tensors,'StringNormalizer':[n for n in nodes if n['operator']=='StringNormalizer'],'external_tensors':[t for t in tensors if t['data_location']=='EXTERNAL' or t['external_data']]}
 assert report['sha256_before']==report['sha256_after'] and report['matches_prior']
 name=('encoder' if 'encoder' in f.name else 'decoder' if 'decoder' in f.name else 'vits')
 (p/(name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');all_reports.append({'model':name,'nodes':len(nodes),'graphs':len(graphs),'functions':len(functions),'operator_kinds':len(counts),'opsets':imports,'tensor_dtypes':dict(collections.Counter(t['dtype'] for t in tensors)),'external_tensors':len(report['external_tensors']),'StringNormalizer_nodes':len(report['StringNormalizer']),'sha256':before})
 print(name,len(nodes),'nodes',len(counts),'operator groups',len(graphs),'graphs')
summary={'parser_onnx':onnx.__version__,'protobuf':google.protobuf.__version__,'load_external_data':False,'inference':False,'shape_inference':False,'models':all_reports}
(p/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))

