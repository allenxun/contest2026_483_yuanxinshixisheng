from pathlib import Path
import ctypes,json,time
import numpy as np
import onnxruntime as ort
r=Path(__file__).resolve().parent
lib=ctypes.CDLL(str(r/'libk7pose.so'))
lib.k7_pose_create.restype=ctypes.c_void_p
lib.k7_pose_destroy.argtypes=[ctypes.c_void_p]
fp=ctypes.POINTER(ctypes.c_float)
lib.k7_pose_infer.argtypes=[ctypes.c_void_p,fp,fp]
lib.k7_pose_arena.argtypes=[ctypes.c_void_p];lib.k7_pose_arena.restype=fp
s=ort.InferenceSession(str(r/'model-inspection/head_pose_fsanet_1x1.onnx'),providers=['CPUExecutionProvider'])
rng=np.random.default_rng(3576)
cases=[np.zeros((1,3,64,64),np.float32),np.ones((1,3,64,64),np.float32),
       -np.ones((1,3,64,64),np.float32)]+[rng.uniform(-1,1,(1,3,64,64)).astype(np.float32) for _ in range(20)]
p=lib.k7_pose_create();assert p
rows=[]
try:
    for x in cases:
        y=np.zeros(3,np.float32);t=time.perf_counter()
        ret=lib.k7_pose_infer(p,x.ctypes.data_as(fp),y.ctypes.data_as(fp))
        elapsed=(time.perf_counter()-t)*1000
        ref=s.run(None,{'input':x})[0].flatten()
        error=float(np.max(np.abs(ref-y)))
        rows.append(dict(native=y.tolist(),reference=ref.tolist(),max_abs_error=error,native_cpu_ms=elapsed))
        assert ret==0 and error<.005,rows[-1]
finally:lib.k7_pose_destroy(p)
(r/'pose-reference-test.json').write_text(json.dumps(dict(execution='HOST_CPU_NOT_K7',cases=rows,
    max_abs_error=max(v['max_abs_error'] for v in rows),accuracy_calibration=False),indent=2))
print('PASS',len(rows),'normalized tensors; max angle difference',max(v['max_abs_error'] for v in rows))
