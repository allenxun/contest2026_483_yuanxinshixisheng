"""Offline graph inventory; neither K7 inference nor an accuracy benchmark."""
import collections
import hashlib
import json
import math
from pathlib import Path

import onnx
from onnx import helper, numpy_helper, shape_inference

root = Path(__file__).resolve().parent / 'model-inspection'
path = root / 'device-v5.onnx'
expected = '218e922d784795901bd5e165e11755898f6c29c4a5724715862aa8cdf1919a8c'
assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
model = onnx.load(str(path))
onnx.checker.check_model(model)
graph = shape_inference.infer_shapes(model).graph

def dims(value):
    return [d.dim_value if d.HasField('dim_value') else None
            for d in value.type.tensor_type.shape.dim]

shapes = {v.name: dims(v) for v in list(graph.input) + list(graph.value_info) + list(graph.output)}
weights = {v.name: list(v.dims) for v in graph.initializer}
conv_macs = 0
unresolved = []
for node in graph.node:
    if node.op_type != 'Conv':
        continue
    output = shapes.get(node.output[0])
    kernel = weights.get(node.input[1])
    if not output or not kernel or None in output or None in kernel:
        unresolved.append(node.name)
        continue
    # Kernel shape is [out_channels, in_channels/group, kh, kw].
    conv_macs += math.prod(output) * math.prod(kernel[1:])

report = {
    'execution': 'OFFLINE_ONNX_GRAPH_INSPECTION_ONLY',
    'model_sha256': expected, 'model_file_bytes': path.stat().st_size,
    'inputs': {v.name: dims(v) for v in graph.input},
    'outputs': {v.name: dims(v) for v in graph.output},
    'nodes': len(graph.node),
    'operators': dict(sorted(collections.Counter(n.op_type for n in graph.node).items())),
    'initializer_bytes': sum(numpy_helper.to_array(v).nbytes for v in graph.initializer),
    'convolution_macs': conv_macs,
    'unresolved_convolutions': unresolved,
    'convolution_macs_exclude': 'elementwise, activation, resize, decode and NMS',
    'k7_runtime_verified': False, 'k7_latency_ms': None,
    'coordinate_contract': 'unmirrored original image; top-left BGR letterbox fill 114; no /255',
}
(root / 'device-graph.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
