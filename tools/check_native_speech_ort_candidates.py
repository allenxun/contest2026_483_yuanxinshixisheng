"""Verify converted candidate loading and actual ORT operator inventory on host."""
import hashlib
import json
import sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'work-in-progress/native-ort-host-converter-python'))
import onnxruntime as ort
from onnxruntime.tools.ort_format_model.utils import create_config_from_models
assert ort.__version__=='1.17.1'
E=R/'evidence/native-speech-ort-load1-20260911'
E.mkdir(exist_ok=False)
models=[]
results=[]
for name in ('encoder','decoder','vits'):
    record=json.loads((R/f'evidence/native-speech-ort-conversion1-20260911/{name}.json').read_text())
    path=Path(record['output'])
    data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==record['output_sha256']
    options=ort.SessionOptions()
    options.intra_op_num_threads=1
    options.inter_op_num_threads=1
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    for key in ('session.use_ort_model_bytes_directly','session.use_ort_model_bytes_for_initializers'):
        options.add_session_config_entry(key,'1')
    session=ort.InferenceSession(data,sess_options=options,providers=['CPUExecutionProvider'])
    io=dict(inputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_inputs()],
            outputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_outputs()])
    assert io==record['io'],name
    del session
    del data
    results.append(dict(model=name,host_load=True,io_match=True,numerical_comparison=False,board_inference=False))
    models.append(path)
    print(name,'HOST_LOAD_IO_PASS',flush=True)
create_config_from_models(models,E/'speech-required.config',enable_type_reduction=False)
create_config_from_models(models[:2],E/'asr-required.config',enable_type_reduction=False)
(E/'result.json').write_text(json.dumps(dict(results=results,ort_version=ort.__version__,
    allocator_note='Host default allocator, not the board model pool; no board heap peak proof.',
    config_sha256=hashlib.sha256((E/'speech-required.config').read_bytes()).hexdigest()),indent=2))
