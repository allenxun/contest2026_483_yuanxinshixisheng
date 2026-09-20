"""Bounded host ORT loading comparison; never a board-memory acceptance test."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
E=R/'evidence/native-ort-bytes-modes1-20260911'

def child(mode):
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001|0x0002|0x8000)
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(45,exit=True)
    sys.path.insert(0,str(R/'work-in-progress/native-ort-host-converter-python'))
    import onnxruntime as ort
    record=json.loads((R/'evidence/native-speech-ort-conversion1-20260911/encoder.json').read_text())
    path=Path(record['output'])
    data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==record['output_sha256']
    options=ort.SessionOptions()
    options.intra_op_num_threads=1
    options.inter_op_num_threads=1
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    if mode in ('direct','both'):
        options.add_session_config_entry('session.use_ort_model_bytes_directly','1')
    if mode=='both':
        options.add_session_config_entry('session.use_ort_model_bytes_for_initializers','1')
    print('BEFORE_SESSION',mode,flush=True)
    session=ort.InferenceSession(str(path) if mode=='path' else data,
                                sess_options=options,providers=['CPUExecutionProvider'])
    print('AFTER_SESSION',mode,flush=True)
    io=dict(inputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_inputs()],
            outputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_outputs()])
    assert io==record['io']
    del session
    faulthandler.cancel_dump_traceback_later()
    print('HOST_LOAD_PASS',mode,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--child',choices=['path','copy','direct','both'])
    a=p.parse_args()
    if a.child:
        child(a.child)
    else:
        E.mkdir(exist_ok=False)
        results=[]
        for mode in ('path','copy','direct','both'):
            with (E/(mode+'.log')).open('wb') as f:
                try:
                    q=subprocess.run([sys.executable,'-X','utf8',__file__,'--child',mode],
                                     stdout=f,stderr=subprocess.STDOUT,timeout=60)
                    item=dict(mode=mode,exit_code=q.returncode,timeout=False)
                except subprocess.TimeoutExpired:
                    item=dict(mode=mode,exit_code=None,timeout=True)
            results.append(item)
            print(json.dumps(item),flush=True)
            (E/'result.json').write_text(json.dumps(dict(results=results,host_only=True,
                board_inference=False,numerical_comparison=False),indent=2))
