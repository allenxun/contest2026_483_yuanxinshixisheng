"""Stage a separate FAT-only increment on the accepted MSC baseline."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R/'work-in-progress/parallel-model-reader-medium/fat-readonly-v1'
E = R/'evidence/fat-readonly-20260910'
E.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(C/'delivery.json') == 'fa02eda95841e6cdd3daf19364a8ec119037b624b62d642311f05af29479d093'
for x in json.loads((C/'delivery.json').read_text())['files']:
    assert sha(C/x['path']) == x['sha256']
changes = {}
for name in ('Kconfig', 'fs_fat32.c', 'fs_fat32attrib.c', 'fs_fat32dirent.c', 'fs_fat32util.c'):
    p = R/'port/tracked/nuttx/fs/fat'/name
    assert not p.exists(), str(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    src = C/'candidate/fat'/name
    p.write_bytes(src.read_bytes())
    changes[p.relative_to(R).as_posix()] = dict(new=sha(p),
        old=sha(R/'evidence/usb-storage-inputs-20260910/nuttx/fs/fat'/name))
with (E/'integration.json').open('x') as f:
    json.dump(dict(files=changes, candidate_delivery_sha256=sha(C/'delivery.json'), hardware_tested=False), f, indent=2)
profile = R/'board/kickpi_k7/configs/velavision_fat_readonly_local/defconfig'
profile.parent.mkdir()
lines = (R/'board/kickpi_k7/configs/velavision_usb_readonly_local/defconfig').read_text().splitlines()
lines = [s for s in lines if s not in ('# CONFIG_FS_FAT is not set',)]
lines += ['CONFIG_FS_FAT=y','CONFIG_FAT_FORCE_READONLY=y','CONFIG_FAT_FORCE_INDIRECT=y',
          '# CONFIG_FAT_COMPUTE_FSINFO is not set','CONFIG_EXAMPLES_K7FAT=y']
profile.write_text('\n'.join(lines)+'\n', newline='\n')
# Predecessor hashes are from a completed build, never the current remote files.
previous = json.loads((R/'private/usb-readonly-20260910/staging.json').read_text())
baseline = {path:item['new'] for path,item in previous.items()}
(R/'private/fat-readonly-original-hashes.json').write_text(json.dumps(baseline,indent=2)+'\n')
for name in ('build_usb_readonly.sh', 'build_usb_readonly_vm.py'):
    s = (R/'tools'/name).read_text().replace('usb-readonly-20260910','fat-readonly-20260910').replace('usb_readonly','fat_readonly').replace('usb-readonly-stage','fat-readonly-stage')
    # Historical USB approval evidence is still a fixed dependency.
    s = s.replace('evidence/sync/fat-readonly-attempt1.json','evidence/sync/usb-readonly-attempt1.json')
    if name.endswith('_vm.py'):
        s = s.replace('private/usb-readonly-original-hashes.json','private/fat-readonly-original-hashes.json')
        extra = list(changes)
        marker = 'paths=list(dict.fromkeys'
        s = s.replace(marker, 'paths += '+repr(extra)+"\npaths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7fat').iterdir()) if p.is_file()]\n"+marker)
        s = s.replace("['CONFIG_USBHOST_MSC=y'", "['CONFIG_FS_FAT=y','CONFIG_FAT_FORCE_READONLY=y','CONFIG_FAT_FORCE_INDIRECT=y','CONFIG_EXAMPLES_K7FAT=y','CONFIG_USBHOST_MSC=y'")
        s = s.replace("assert 'CONFIG_FS_FAT=y' not in (B/'.config').read_text().splitlines()", "assert 'CONFIG_FAT_COMPUTE_FSINFO=y' not in (B/'.config').read_text().splitlines()")
    dest = R/'tools'/name.replace('usb_readonly','fat_readonly')
    with dest.open('x',newline='\n') as f: f.write(s)
print('FAT core staged; probe/lifecycle integration required before build')
