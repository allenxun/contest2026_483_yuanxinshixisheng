"""Freeze an opset14 Add probe matching the ASR kernel registration set."""
import sys,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'work-in-progress/native-ort-host-converter-python'))
import onnx
assert onnx.__version__=='1.16.2'
old=R/'work-in-progress/native-ort-add-probe';new=R/'work-in-progress/native-ort-asr-add-probe';new.mkdir()
raw=(old/'add.onnx').read_bytes();assert hashlib.sha256(raw).hexdigest()=='f0ab8a49f72351be2010f51c35e10bd69d82c1dd0e8e8d95fd0db4cd42a4453f'
m=onnx.load_model_from_string(raw);assert len(m.opset_import)==1 and m.opset_import[0].version==13
m.opset_import[0].version=14;onnx.checker.check_model(m);data=m.SerializeToString()
(new/'add.onnx').write_bytes(data)
(new/'add_probe.c').write_bytes((old/'add_probe.c').read_bytes())
(new/'add_model.h').write_text('#ifndef K7_ADD_MODEL_H\n#define K7_ADD_MODEL_H\nstatic const unsigned char k7_add_model[] = {\n'+','.join('0x%02x'%x for x in data)+'\n};\n#endif\n')
(new/'manifest.json').write_text(json.dumps(dict(opset=14,ir=m.ir_version,onnx_checker_passed=True,model_run=False,sha256=hashlib.sha256(data).hexdigest()),indent=2))
s=(R/'tools/compile_native_add_probe.py').read_text().replace('native-add-probe','native-asr-add-probe').replace('native-ort-add-probe','native-ort-asr-add-probe')
(R/'tools/compile_native_asr_add_probe.py').write_text(s)
