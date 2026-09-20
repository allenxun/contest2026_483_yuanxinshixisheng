"""Read the live SDK and export project-owned sources plus tracked patches.
Run in the existing Ubuntu SDK. No device operations or Git commits.
"""
import hashlib, json, subprocess, tarfile
from pathlib import Path

SDK = Path('/home/swl/openvela')
OUT = SDK / 'work/velavision-integration-20260909'
OUT.mkdir(parents=True, exist_ok=True)
items = []

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def add(src, dest):
    if not src.is_file() or src.is_symlink(): return
    items.append((src, dest))
def tree(src, dest):
    for p in sorted(src.rglob('*')):
        if any(x in ('__pycache__', '.git', 'build', 'build-sdk') for x in p.relative_to(src).parts): continue
        if p.suffix in ('.o', '.a', '.so', '.pyc'): continue
        add(p, str(Path(dest) / p.relative_to(src)))

repos = {}
for name in ('nuttx', 'apps'):
    repo = SDK / name
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True)
    diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'])
    (OUT / (name + '.patch')).write_bytes(diff)
    add(OUT / (name + '.patch'), 'patches/' + name + '.patch')
    repos[name] = dict(head=head, status=status, tracked_patch_sha256=sha(OUT / (name + '.patch')))
    changed = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only', 'HEAD'], text=True).splitlines()
    for rel in changed:
        add(repo / rel, 'port/tracked/' + name + '/' + rel)
for name in ('gimbal', 'k7host', 'k7npu', 'k7radio', 'k7usb'):
    tree(SDK / 'apps/examples' / name, 'app/' + name)
for rel in ('arch/arm64/include/rk3576', 'arch/arm64/src/rk3576'):
    tree(SDK / 'nuttx' / rel, 'port/new/nuttx/' + rel)
tree(SDK / 'nuttx/boards/arm64/rk3576/kickpi_k7', 'board/kickpi_k7')
untracked = subprocess.check_output(['git', '-C', str(SDK / 'nuttx'), 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
for rel in untracked:
    if rel.startswith(('drivers/usbhost/', 'include/nuttx/usb/')):
        add(SDK / 'nuttx' / rel, 'port/new/nuttx/' + rel)
for profile in ('rk3576_usb_photo_direction', 'rk3576_npu_raw_vendor', 'rk3576_radio_id36'):
    for name in ('.config', 'nuttx.bin'):
        add(SDK / 'cmake_out' / profile / name, 'baselines/' + profile + '/' + name)
for name in ('photo_controller.py', 'photo_preview.py', 'photo_protocol.py', 'k7_video_receiver.py', 'track_overlay.py', 'manual_model.py',
             'test_photo_controller.py', 'test_photo_protocol.py', 'test_fusion.c', 'generate_pose.py',
             'test_pose_reference.py', 'HEAD_POSE_NOTICES.md', 'FSA_NET_PYTORCH_MIT.txt', 'calibration.json',
             'NPU_ADAPTATION_PLAN.md', 'inspect_device_model.py', 'prepare_device_rknn.py'):
    add(SDK / 'work/rk3576-fusion' / name, 'host/vision/' + name)
# These are protocol/control prerequisites used by the accepted host scripts.
for dirname in ('rk3576-preview', 'rk3576-xcenter-follow', 'rk3576-usbhost'):
    source = SDK / 'work' / dirname
    for pattern in ('*.py', '*.json', '*NOTICES*', '*LICENSE*'):
        for p in sorted(source.glob(pattern)):
            if p.stat().st_size < 1000000:
                add(p, 'host/support/' + dirname + '/' + p.name)
inventory = dict(captured_from=str(SDK), repositories=repos, files=[dict(source=str(src.relative_to(SDK)),
                 path=dest, bytes=src.stat().st_size, sha256=sha(src)) for src, dest in items])
(OUT / 'sdk-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
add(OUT / 'sdk-inventory.json', 'evidence/sdk-inventory.json')
archive = OUT / 'project-sources.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    for src, dest in items: tar.add(src, arcname=dest, recursive=False)
print(json.dumps(dict(archive=str(archive), bytes=archive.stat().st_size, files=len(items), sha256=sha(archive))))
