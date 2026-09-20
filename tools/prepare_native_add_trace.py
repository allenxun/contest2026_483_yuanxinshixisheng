"""Preserve the loaded Add input and create an independently compiled trace candidate."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'work-in-progress/native-ort-add-probe'
target = root / 'work-in-progress/native-ort-add-trace'
target.mkdir(exist_ok=False)
inputs = {name: (source / name).read_bytes()
          for name in ('add_probe.c', 'add_model.h', 'add.onnx')}
code = inputs['add_probe.c'].decode()
code = code.replace('  const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);',
                    '  puts("ORT_ADD BEGIN api"); fflush(stdout);\n'
                    '  const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);\n'
                    '  puts("ORT_ADD END api"); fflush(stdout);')
old = '#define CHECK(label, call) do { stage = label; status = (call);'
assert code.count(old) == 1
code = code.replace(old,
    '#define CHECK(label, call) do { stage = label; '
    'printf("ORT_ADD BEGIN %s\\n", stage); fflush(stdout); '
    'status = (call); printf("ORT_ADD END %s\\n", stage); fflush(stdout);')
code = code.replace('cleanup:\n',
                    'cleanup:\n  puts("ORT_ADD BEGIN cleanup"); fflush(stdout);\n')
for name, data in inputs.items():
    (target / name).write_bytes(code.encode() if name == 'add_probe.c' else data)
report = dict(inputs={n: hashlib.sha256(b).hexdigest() for n, b in inputs.items()},
              outputs={n: hashlib.sha256((target / n).read_bytes()).hexdigest() for n in inputs},
              compiled=False, hardware_tested=False,
              purpose='Locate last returned C API call; same model, thread count and cleanup semantics')
assert all((source / n).read_bytes() == b for n, b in inputs.items())
(target / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
driver = (root / 'tools/compile_native_add_probe.py').read_text()
driver = driver.replace('native-add-probe', 'native-add-trace').replace(
    'native-ort-add-probe', 'native-ort-add-trace')
(root / 'tools/compile_native_add_trace.py').write_text(driver)
print(json.dumps(report, indent=2))
