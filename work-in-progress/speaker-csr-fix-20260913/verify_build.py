"""Isolate a one-line playback fix; retain old firmware and runtime."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
SDK = Path('/home/swl/openvela')
OLD = 'ebbfc2e206448e2f945449c95660fb9d024c371147c3f8c3c3816bb9b6ef896c'
BUILD = SDK / 'cmake_out/velavision_speaker_csr_20260913'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def run(cmd, name, env=None, cwd=None):
    with (HERE / (name + '.log')).open('xb') as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                            cwd=cwd, env=env, timeout=2400).returncode
    print(name, rc, flush=True)
    return rc

def main():
    report = {'hardware_tested': False, 'tests': []}
    for level in ('-O0', '-O2'):
        for variant in ('before', 'fixed'):
            exe = HERE / (variant + level)
            command = ['gcc', '-std=c11', level, '-Wall', '-Wextra', '-Werror',
                       '-I' + str(PROJECT / 'app/k7sound'),
                       str(HERE / ('pio-' + variant + '.c')),
                       str(HERE / 'test_playback.c'), '-o', str(exe)]
            assert run(command, 'compile-' + variant + level) == 0
            rc = run([str(exe)], 'test-' + variant + level)
            assert (rc == 0) == (variant == 'fixed')
            report['tests'].append({'variant': variant, 'optimization': level,
                                    'exit_code': rc})
    # Read-only SDK-wide audit is retained, never used to bless unknown edits.
    report['sync_audit_exit'] = run(['python3', str(PROJECT / 'tools/sync_sdk.py'),
                                   '--sdk', str(SDK), '--check'], 'sync-audit')
    for p in (PROJECT / 'app/k7sound/pio.c', SDK / 'apps/examples/k7sound/pio.c'):
        if sha(p) != OLD:
            raise RuntimeError('unexpected preexisting source: ' + str(p))
    prior = json.loads((PROJECT / 'work-in-progress/voice-rule-provision-20260912/result.json').read_text())
    configure = prior['configure_command'][:]
    runtime = Path(next(x.split('=', 1)[1] for x in configure if x.startswith('-DK7VOICE_ORT_OBJECT=')))
    assert sha(runtime) == prior['runtime_sha256']
    if BUILD.exists():
        raise RuntimeError('refuse overwriting independent build')
    for p in (PROJECT / 'app/k7sound/pio.c', SDK / 'apps/examples/k7sound/pio.c'):
        p.write_bytes((HERE / 'pio-fixed.c').read_bytes())
    report['source_before'] = OLD
    report['source_after'] = sha(HERE / 'pio-fixed.c')
    report['unchanged_runtime'] = sha(runtime)
    configure[configure.index('-B') + 1] = str(BUILD)
    env = dict(os.environ)
    env['PATH'] = ':'.join(str(SDK / p) for p in (
        'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin',
        'prebuilts/tools/python/bin', 'prebuilts/build-tools/linux-x86_64/bin')) + ':' + env['PATH']
    env['PYTHONPATH'] = str(SDK / 'prebuilts/tools/python/dist-packages/kconfiglib')
    report['configure_exit'] = run(configure, 'configure', env, SDK)
    if report['configure_exit'] == 0:
        report['build_exit'] = run(['cmake', '--build', str(BUILD), '-j4'], 'build', env, SDK)
        if report['build_exit'] == 0:
            report['artifacts'] = {n: {'sha256': sha(BUILD / n), 'bytes': (BUILD / n).stat().st_size}
                                   for n in ('nuttx', 'nuttx.bin', '.config')}
    (HERE / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)

if __name__ == '__main__':
    main()
