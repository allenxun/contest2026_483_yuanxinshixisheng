"""Archive a manifest, then remove obsolete reproducible VM build trees.

The current voice/TLS build and the latest Wi-Fi build stay intact.  This tool
has a two-step plan/apply gate so the manifest is copied to the Windows project
before any recursive deletion takes place.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT / "evidence" / "vm-space-cleanup-20260912-round3"
EVIDENCE.mkdir(parents=True, exist_ok=True)

REMOTE = r'''
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path('/home/swl/openvela/cmake_out')
OUT = Path('/home/swl/openvela/work/space-cleanup-20260912-round3')
KEEP = {
    'velavision_voice_tls_20260911',
    'velavision_wifi_arp_20260909',
}
KEY_FILES = ('.config', 'nuttx', 'nuttx.bin', 'CMakeCache.txt', 'build.ninja')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def available_bytes():
    stat = os.statvfs(str(ROOT))
    return stat.f_bavail * stat.f_frsize


def assert_idle():
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            cwd = (process / 'cwd').resolve(strict=True)
            command = (process / 'cmdline').read_bytes()
        except (OSError, RuntimeError):
            continue
        if cwd == ROOT or ROOT in cwd.parents:
            raise RuntimeError('active process cwd inside build root: ' + process.name)
        if any(token in command for token in (b'ninja', b'cmake', b'ccache')):
            if str(ROOT).encode() in command:
                raise RuntimeError('active build references build root: ' + process.name)


def describe(directory):
    resolved = directory.resolve(strict=True)
    if resolved.parent != ROOT or resolved == ROOT or directory.is_symlink():
        raise RuntimeError('unsafe build directory: ' + str(directory))
    record = {
        'name': directory.name,
        'path': str(resolved),
        'mtime_ns': directory.stat().st_mtime_ns,
        'key_files': {},
    }
    for name in KEY_FILES:
        path = directory / name
        if path.is_file() and not path.is_symlink():
            record['key_files'][name] = {
                'bytes': path.stat().st_size,
                'sha256': sha256(path),
            }
    return record


def current_targets():
    targets = []
    for directory in sorted(ROOT.iterdir()):
        if not directory.is_dir() or directory.is_symlink() or directory.name in KEEP:
            continue
        targets.append(describe(directory))
    return targets


ROOT = ROOT.resolve(strict=True)
if str(ROOT) != '/home/swl/openvela/cmake_out':
    raise RuntimeError('unexpected build root')
OUT.mkdir(parents=True, exist_ok=True)
assert_idle()

if sys.argv[1] == 'plan':
    plan_path = OUT / 'plan.json'
    if plan_path.exists():
        raise RuntimeError('plan already exists')
    targets = current_targets()
    plan = {
        'root': str(ROOT),
        'keep': sorted(KEEP),
        'target_count': len(targets),
        'targets': targets,
        'available_before': available_bytes(),
        'scope': (
            'Remove complete obsolete CMake/Ninja build trees only. Sources, '
            'models, SDK, project mirror, logs and current voice/Wi-Fi builds stay.'
        ),
    }
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True))
    print(json.dumps({
        'target_count': len(targets),
        'keep': sorted(KEEP),
        'available_before': plan['available_before'],
        'plan_sha256': sha256(plan_path),
    }))
elif sys.argv[1] == 'apply':
    plan_path = OUT / 'plan.json'
    expected_hash = sys.argv[2]
    if sha256(plan_path) != expected_hash:
        raise RuntimeError('plan hash mismatch')
    applied_path = OUT / 'applied.json'
    if applied_path.exists():
        raise RuntimeError('cleanup already applied')
    plan = json.loads(plan_path.read_text())
    if plan['root'] != str(ROOT) or set(plan['keep']) != KEEP:
        raise RuntimeError('plan scope mismatch')
    by_name = {item['name']: item for item in current_targets()}
    planned = {item['name']: item for item in plan['targets']}
    if set(by_name) != set(planned):
        raise RuntimeError('target set changed after planning')
    for name, before in planned.items():
        now = by_name[name]
        if now['path'] != before['path'] or now['key_files'] != before['key_files']:
            raise RuntimeError('protected key files changed: ' + name)
    assert_idle()
    deleted = []
    for item in plan['targets']:
        path = Path(item['path']).resolve(strict=True)
        if path.parent != ROOT or path.name in KEEP or path == ROOT:
            raise RuntimeError('unsafe deletion target: ' + str(path))
        shutil.rmtree(str(path))
        deleted.append(path.name)
    result = {
        'deleted_count': len(deleted),
        'deleted': deleted,
        'kept': sorted(KEEP),
        'available_before': plan['available_before'],
        'available_after': available_bytes(),
        'plan_sha256': expected_hash,
        'note': 'Key artifacts for selected baselines were copied to Windows E: before apply.',
    }
    applied_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result))
else:
    raise SystemExit('expected plan or apply')
'''

SSH_OPTIONS = [
    "-i",
    "C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=12",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--plan-hash")
    args = parser.parse_args()
    if args.mode == "apply":
        if not args.plan_hash or len(args.plan_hash) != 64:
            raise SystemExit("--plan-hash is required for apply")
        int(args.plan_hash, 16)
    remote_args = [args.mode]
    if args.plan_hash:
        remote_args.append(args.plan_hash)
    process = subprocess.run(
        ["ssh.exe", *SSH_OPTIONS, "swl@192.168.152.131", "python3 - " + " ".join(remote_args)],
        input=REMOTE,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (EVIDENCE / (args.mode + ".log")).write_text(process.stdout, encoding="utf-8")
    print(process.stdout, end="")
    if process.returncode:
        raise SystemExit(process.returncode)
    names = ("plan.json",) if args.mode == "plan" else ("applied.json",)
    for name in names:
        subprocess.run(
            [
                "scp.exe",
                *SSH_OPTIONS,
                "swl@192.168.152.131:/home/swl/openvela/work/space-cleanup-20260912-round3/" + name,
                str(EVIDENCE / name),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
