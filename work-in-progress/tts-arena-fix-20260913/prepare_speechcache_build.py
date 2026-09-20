"""Apply one hash-guarded SDK source update and build the cached runtime."""

import hashlib
import shutil
import subprocess
from pathlib import Path


SDK = Path('/home/swl/openvela')
PROJECT = SDK / 'work/velavision-project'
HERE = PROJECT / 'work-in-progress/tts-arena-fix-20260913'
FORMAL_SOUND = PROJECT / 'app/k7sound/k7sound_main.c'
SDK_SOUND = SDK / 'apps/examples/k7sound/k7sound_main.c'
EXPECTED_PREVIOUS = '77b6b9d657720cd916a4083540e39577dbc92b2a14f47a95d0e8e39a4564c773'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


actual = sha(SDK_SOUND)
if actual != EXPECTED_PREVIOUS and actual != sha(FORMAL_SOUND):
    raise RuntimeError('SDK k7sound contains an unknown change: ' + actual)
if actual == EXPECTED_PREVIOUS:
    shutil.copyfile(FORMAL_SOUND, SDK_SOUND)
if sha(SDK_SOUND) != sha(FORMAL_SOUND):
    raise RuntimeError('SDK k7sound synchronization failed')
subprocess.run(['python3', str(HERE / 'build_speechcache_runtime.py')],
               cwd=HERE, check=True)
