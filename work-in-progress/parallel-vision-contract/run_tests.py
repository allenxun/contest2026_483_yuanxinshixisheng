"""Bounded host-only build/replay, preserve every run and input hash snapshot."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INPUTS = ['../AGENTS.md', 'README.md', 'project-manifest.json',
 'docs/代码日志对应表.md', 'docs/README历史快照_20260910_块设备前.md',
 'docs/构建与集成说明.md', 'docs/机器人目标与Agent接入位置_20260909.md',
 'docs/官方硬件赛道对齐与目标_20260909.md',
 'app/k7host/k7_yunet.h', 'app/k7host/k7_yunet.c',
 'app/k7host/k7_track.h', 'app/k7host/k7_track.c',
 'app/k7host/k7_pipeline.h', 'app/k7host/k7_pipeline.c',
 'app/k7host/k7_photo.h', 'app/k7host/k7_photo.c',
 'app/k7host/k7host_main.c', 'app/k7host/fusion_core.h',
 'host/vision/NPU_ADAPTATION_PLAN.md', 'host/vision/photo_controller.py',
 'host/vision/photo_protocol.py', 'host/vision/photo_preview.py',
 'legacy/pc-delivery/pc_demo/models/device/manifest.json',
 'legacy/pc-delivery/pc_demo/vendor/target_detection/pipeline.py',
 'legacy/pc-delivery/pc_demo/vendor/target_detection/runtime.py',
 'work-in-progress/parallel-vision-contract/vision_contract.h',
 'work-in-progress/parallel-vision-contract/vision_contract.c',
 'work-in-progress/parallel-vision-contract/test_contract.c',
 'work-in-progress/parallel-vision-contract/run_tests.py']
def snapshot():
    return [{'path': str((ROOT / p).resolve()),
             'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}
            for p in INPUTS]
def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = HERE / 'evidence' / stamp
    dest.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    (dest / 'inputs.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf8')
    gcc = r'D:\software\mingw64\mingw64\bin\gcc.exe'
    commands = [[gcc, '--version'],
       [gcc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
        '-I'+str(ROOT/'app/k7host'), str(HERE/'vision_contract.c'),
        str(HERE/'test_contract.c'), str(ROOT/'app/k7host/k7_track.c'),
        '-lm', '-o', str(dest/'test_contract.exe')],
       [str(dest/'test_contract.exe')]]
    runs = []
    for cmd in commands:
        try:
            p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=30)
            runs.append(dict(command=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr))
        except (OSError, subprocess.TimeoutExpired) as exc:
            runs.append(dict(command=cmd, returncode=None, error=str(exc)))
        if runs[-1]['returncode'] != 0:
            break
    after = snapshot()
    result = dict(utc=stamp, python=sys.version, host_only=True, synthetic_replay=True,
                  model_inference=False, input_unchanged=before==after, runs=runs,
                  passed=len(runs)==3 and all(r['returncode']==0 for r in runs) and before==after)
    (dest/'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2))
    print('Evidence:', dest)
    return 0 if result['passed'] else 1
if __name__ == '__main__':
    sys.exit(main())
