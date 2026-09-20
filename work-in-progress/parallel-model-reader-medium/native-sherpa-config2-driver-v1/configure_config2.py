"""Parent-run Linux configuration driver. No SSH; default validates and prints only."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
SIX = {'kaldi-native-fbank', 'kaldi-decoder', 'kissfft', 'ssentencepiece', 'cppjieba', 'eigen'}

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def verify_sources(root, manifest, names):
    records = json.loads(manifest.read_text())
    selected = {}
    for key, value in records.items():
        parts = key.replace('\\', '/').split('/')
        if parts[0] != 'sources' or parts[1] not in names:
            continue
        if '..' in parts or any(not x for x in parts):
            raise ValueError('invalid manifest path')
        p = root.joinpath(*parts[1:])
        if p.is_symlink() or not p.is_file() or digest(p) != value['sha256']:
            raise ValueError('source mismatch: ' + str(p))
        selected['/'.join(parts[1:])] = value['sha256']
    actual = set()
    for name in names:
        for p in (root / name).rglob('*'):
            if p.is_symlink():
                raise ValueError('source symlink: ' + str(p))
            if p.is_file():
                actual.add(p.relative_to(root).as_posix())
    if not selected or actual != set(selected):
        raise ValueError('source manifest membership mismatch')
    return selected

def command(a, archives):
    if a.build.exists() or a.output.exists():
        raise ValueError('new build AND output directories required')
    return [str(a.cmake), '-S', str(a.stage / 'sherpa'), '-B', str(a.build), '-G', 'Ninja',
        '-DK7_SHERPA_DEPS_ROOT=' + str(a.stage / 'sources'),
        '-C', str(HERE / 'asr-initial-cache.cmake'),
        '-DFETCHCONTENT_SOURCE_DIR_KALDIFST=' + str(a.corrected / 'kaldifst'),
        '-DFETCHCONTENT_SOURCE_DIR_OPENFST=' + str(a.corrected / 'openfst'),
        '-C', str(HERE / 'eigen-cache.cmake'),
        '-DCMAKE_TOOLCHAIN_FILE=' + str(a.ort / 'session-toolchain.cmake'),
        '-DCMAKE_BUILD_TYPE=MinSizeRel', '-DCMAKE_MAKE_PROGRAM=' + str(a.ninja),
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
        '-DK7_ORT_PUBLIC_INCLUDE_DIR=' + str(a.ort / 'ort/include/onnxruntime/core/session'),
        '-DK7_ORT_STATIC_LIBRARIES=' + ';'.join(str(p) for p in archives)]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', type=Path, required=True)
    p.add_argument('--corrected', type=Path, required=True, help='v3 sources directory, not its parent')
    p.add_argument('--ort', type=Path, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cmake', type=Path, required=True)
    p.add_argument('--ninja', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    for name in ('stage', 'corrected', 'ort', 'build', 'output', 'cmake', 'ninja'):
        setattr(a, name, getattr(a, name).resolve())
    verify_sources(a.stage / 'sources', HERE / 'v1-source-manifest.json', SIX)
    verify_sources(a.corrected, HERE / 'v3-source-manifest.json', {'kaldifst', 'openfst'})
    result = a.ort / 'compile-attempt6/result.json'
    if json.loads(result.read_text())['exit_code'] != 0:
        raise ValueError('ORT compile-attempt6 not successful')
    archives = sorted((a.ort / 'build').rglob('*.a'))
    if not any(x.name == 'libonnxruntime_session.a' for x in archives):
        raise ValueError('real ORT Session archive missing')
    for x in archives:
        with x.open('rb') as f:
            if f.read(8) != b'!<arch>\n':
                raise ValueError('not regular archive: ' + str(x))
    cmd = command(a, archives)
    print(shlex.join(cmd), flush=True)
    if not a.execute:
        return
    a.output.mkdir(parents=True, exist_ok=False)
    metadata = dict(command=cmd, archives=[dict(path=str(x), sha256=digest(x)) for x in archives],
        toolchain_sha256=digest(a.ort / 'session-toolchain.cmake'),
        ort_compile_result_sha256=digest(result), compiled=False, model_run=False)
    (a.output / 'inputs.json').write_text(json.dumps(metadata, indent=2))
    try:
        with (a.output / 'configure.log').open('wb') as log:
            q = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        metadata['exit_code'] = q.returncode
    except subprocess.TimeoutExpired:
        metadata['exit_code'] = None
        metadata['timeout'] = True
    finally:
        (a.output / 'result.json').write_text(json.dumps(metadata, indent=2))
    raise SystemExit(metadata.get('exit_code') if metadata.get('exit_code') is not None else 124)

if __name__ == '__main__':
    main()
