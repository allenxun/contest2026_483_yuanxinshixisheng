import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

H = Path(__file__).resolve().parent
P = H.parent
R = P.parents[1]
inputs = {}
for src, dest in [
    (P/'native-sherpa-offline-stage-v1/asr-initial-cache.cmake', 'asr-initial-cache.cmake'),
    (P/'native-sherpa-offline-stage-v3/eigen-cache.cmake', 'eigen-cache.cmake'),
    (P/'native-sherpa-offline-stage-v1/source-manifest.json', 'v1-source-manifest.json'),
    (P/'native-sherpa-offline-stage-v3/source-manifest.json', 'v3-source-manifest.json'),
    (R/'tools/configure_native_sherpa_asr.py', 'config1-reference.py.txt')]:
    b = src.read_bytes()
    inputs[str(src)] = hashlib.sha256(b).hexdigest()
    (H/dest).write_bytes(b)
(H/'inputs.json').write_text(json.dumps(inputs, indent=2))
spec = importlib.util.spec_from_file_location('driver', H/'configure_config2.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
results = []
for version, names in [('v1', m.SIX), ('v3', {'kaldifst', 'openfst'})]:
    selected = m.verify_sources(P/f'native-sherpa-offline-stage-{version}/sources', H/f'{version}-source-manifest.json', names)
    results.append(dict(test='actual-source-hash-'+version, files=len(selected), passed=True))
with tempfile.TemporaryDirectory(dir=H) as td:
    t = Path(td)
    a = SimpleNamespace(build=t/'new-build', output=t/'new-output', cmake=Path('/cmake'),
        stage=Path('/old-stage'), corrected=Path('/v3/sources'), ort=Path('/real-ort'), ninja=Path('/ninja'))
    cmd = m.command(a, [Path('/real-ort/build/libonnxruntime_session.a')])
    assert '-DFETCHCONTENT_SOURCE_DIR_KALDIFST=' + str(a.corrected/'kaldifst') in cmd
    assert '-DFETCHCONTENT_SOURCE_DIR_OPENFST=' + str(a.corrected/'openfst') in cmd
    assert cmd.index(str(H/'eigen-cache.cmake')) > cmd.index(str(H/'asr-initial-cache.cmake'))
    assert not any('standard_math' in x.lower() for x in cmd)
    assert '-DK7_SHERPA_DEPS_ROOT=' + str(a.stage/'sources') in cmd
    results.append(dict(test='command-order-and-no-fake-results', passed=True))
    for key in ('build', 'output'):
        getattr(a, key).mkdir()
        try:
            m.command(a, [])
            raise AssertionError('existing directory accepted')
        except ValueError:
            pass
        getattr(a, key).rmdir()
    results.append(dict(test='reject-existing-build-and-output', passed=True))
    (t/'dep').mkdir()
    (t/'dep/f').write_bytes(b'original')
    manifest=t/'manifest.json'
    manifest.write_text(json.dumps({'sources/dep/f': {'sha256': m.digest(t/'dep/f')}}))
    m.verify_sources(t, manifest, {'dep'})
    (t/'dep/f').write_bytes(b'changed')
    try:
        m.verify_sources(t, manifest, {'dep'})
        raise AssertionError('changed source accepted')
    except ValueError:
        pass
    results.append(dict(test='reject-changed-source', passed=True))
(H/'test-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))

