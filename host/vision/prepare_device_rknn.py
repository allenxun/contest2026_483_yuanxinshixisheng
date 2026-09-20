"""Prepare an RK3576 candidate; conversion/simulator evidence is not board acceptance."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
import traceback

import numpy as np
import onnx
import onnxruntime as ort
from rknn.api import RKNN

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'model-inspection/device-v5-raw-opset12.onnx'
OUT = ROOT / 'npu-candidate'
EXPECTED = '30e1782cd50c1ebb9e760ebf033ad4126db0a1f21fa7f7a507b91bfc22357375'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    target = OUT / 'device_v5_rk3576_fp16.rknn'
    if target.exists():
        raise RuntimeError('Existing candidate retained; choose a new output directory for reruns')
    report = dict(status='started', source_sha256=sha(SOURCE),
                  target_platform='rk3576', quantized=False,
                  hardware_verified=False, openvela_runtime_available=False,
                  input_contract=dict(color='BGR', shape=[1,640,640,3],
                                      layout='NHWC', dtype='uint8', mean=0, std=1,
                                      letterbox='top_left', fill=114),
                  validation_scope='Synthetic PC simulator numerical smoke only; no real-image accuracy or board timing',
                  versions={p: importlib.metadata.version(p) for p in
                            ('rknn-toolkit2','onnx','onnxruntime','numpy')},
                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  comparisons=[])
    rknn = None
    try:
        assert report['source_sha256'] == EXPECTED, 'Source hash differs'
        graph = onnx.load(str(SOURCE))
        onnx.checker.check_model(graph)
        expected_shapes = [[1,6,80,80],[1,6,40,40],[1,6,20,20]]
        report['outputs'] = [v.name for v in graph.graph.output]
        rknn = RKNN(verbose=False)
        result = rknn.config(target_platform='rk3576', mean_values=[[0,0,0]],
                             std_values=[[1,1,1]], optimization_level=3)
        assert result in (0,None), ('config', result)
        assert rknn.load_onnx(model=str(SOURCE)) == 0, 'load_onnx failed'
        # No INT8 calibration data has been supplied. Do not use smoke inputs as calibration.
        assert rknn.build(do_quantization=False) == 0, 'build failed'
        assert rknn.export_rknn(str(target)) == 0, 'export failed'
        report.update(status='converted', artifact_sha256=sha(target),
                      artifact_bytes=target.stat().st_size)
        (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        assert rknn.init_runtime() == 0, 'PC simulator init failed'
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(str(SOURCE), options, providers=['CPUExecutionProvider'])
        for name in ('gray','gradient'):
            raw = np.full((1,640,640,3), 114, np.uint8)
            if name == 'gradient':
                yy,xx = np.indices((480,640))
                raw[0,:480] = np.stack((xx%256,yy%256,(xx+yy)%256), axis=-1).astype(np.uint8)
            expected = session.run(None, {session.get_inputs()[0].name:
                                         np.ascontiguousarray(raw.transpose(0,3,1,2),dtype=np.float32)})
            actual = rknn.inference(inputs=[raw], data_format='nhwc')
            assert actual is not None and len(actual)==3, 'Output count differs'
            metrics=[]
            for i,(ref,got) in enumerate(zip(expected,actual)):
                assert list(ref.shape)==list(got.shape)==expected_shapes[i], 'Shape differs'
                assert np.isfinite(ref).all() and np.isfinite(got).all(), 'Non-finite output'
                a,b = ref.astype(np.float64).ravel(), np.asarray(got,dtype=np.float64).ravel()
                delta = a-b
                metrics.append(dict(output=report['outputs'][i],shape=list(ref.shape),
                                    max_abs_error=float(np.max(np.abs(delta))),
                                    rmse=float(np.sqrt(np.mean(delta*delta))),
                                    cosine_similarity=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))))
            report['comparisons'].append(dict(sample=name,outputs=metrics))
        report['status']='converted_and_pc_smoke_compared'
        return 0
    except Exception as exc:
        report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
        traceback.print_exc()
        return 1
    finally:
        if rknn is not None:
            rknn.release()
        report['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2),flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
