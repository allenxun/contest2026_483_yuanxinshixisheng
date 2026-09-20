"""Generate/check an actual ONNX Add artifact; never claim host checks as inference."""
import hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'work-in-progress/native-model-parser-python'))
import onnx
from onnx import helper,TensorProto
O=R/'work-in-progress/native-ort-add-probe';O.mkdir(exist_ok=True)
graph=helper.make_graph([helper.make_node('Add',['a','b'],['y'])],'k7_add',
 [helper.make_tensor_value_info('a',TensorProto.FLOAT,[4]),helper.make_tensor_value_info('b',TensorProto.FLOAT,[4])],
 [helper.make_tensor_value_info('y',TensorProto.FLOAT,[4])])
model=helper.make_model(graph,producer_name='VelaVision-native-gate',opset_imports=[helper.make_opsetid('',13)])
model.ir_version=8
onnx.checker.check_model(model)
data=model.SerializeToString();(O/'add.onnx').write_bytes(data)
lines=[','.join('0x%02x'%x for x in data[i:i+16]) for i in range(0,len(data),16)]
(O/'add_model.h').write_text('#ifndef K7_ADD_MODEL_H\n#define K7_ADD_MODEL_H\nstatic const unsigned char k7_add_model[] = {\n'+',\n'.join(lines)+'\n};\n#endif\n')
(O/'model.json').write_text(json.dumps(dict(generator_onnx=onnx.__version__,ir=8,opset=13,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
 host_schema_check=True,host_inference=False,target_inference=False,expected=[11,22,33,44]),indent=2))
print('ONNX structural check passed',len(data),hashlib.sha256(data).hexdigest())
