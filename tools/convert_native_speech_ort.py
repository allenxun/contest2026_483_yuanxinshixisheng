"""Create separate ORT-format candidates; source models stay untouched.

Host conversion/session loading is not board inference or numerical acceptance.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
E = R/'evidence/native-speech-ort-conversion1-20260911'
M = R/'work-in-progress/native-speech-ort-models1'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def child(name):
    sys.path.insert(0,str(R/'work-in-progress/native-ort-host-converter-python'))
    import onnxruntime as ort
    assert ort.__version__ == '1.17.1'
    source = json.loads((R/f'work-in-progress/parallel-model-reader-medium/native-speech-model-ops-v2/{name}.json').read_text())
    path = Path(source['path'])
    before = sha(path)
    assert before == source['sha256_before'] == source['sha256_after']
    output = M/(name+'.ort')
    assert not output.exists()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    options.add_session_config_entry('session.save_model_format','ORT')
    options.optimized_model_filepath = str(output)
    started = time.monotonic()
    session = ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    io = dict(inputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_inputs()],
              outputs=[dict(name=x.name,shape=x.shape,type=x.type) for x in session.get_outputs()])
    del session
    after = sha(path)
    assert before == after
    with output.open('rb') as f:
        assert f.read(8)[4:8] == b'ORTM'
    result = dict(model=name,source=str(path),source_sha256=before,source_unchanged=True,
                  output=str(output),output_bytes=output.stat().st_size,output_sha256=sha(output),
                  ort_version=ort.__version__,optimization='ORT_DISABLE_ALL',providers=['CPUExecutionProvider'],
                  seconds=time.monotonic()-started,io=io,host_conversion=True,numerical_comparison=False,
                  board_loaded=False,board_inference=False)
    (E/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',choices=['encoder','decoder','vits'])
    args=parser.parse_args()
    if args.child:
        child(args.child)
    else:
        E.mkdir(exist_ok=False)
        M.mkdir(exist_ok=False)
        results=[]
        for name in ('encoder','decoder','vits'):
            with (E/(name+'.log')).open('wb') as stream:
                try:
                    p=subprocess.run([sys.executable,'-X','utf8',__file__,'--child',name],
                                     stdout=stream,stderr=subprocess.STDOUT,timeout=180)
                    results.append(dict(model=name,exit_code=p.returncode,timeout=False))
                except subprocess.TimeoutExpired:
                    results.append(dict(model=name,exit_code=None,timeout=True))
            print(json.dumps(results[-1]),flush=True)
            if results[-1]['exit_code'] != 0:
                break
        (E/'result.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        if len(results)!=3 or any(x['exit_code']!=0 for x in results):
            raise SystemExit(1)
