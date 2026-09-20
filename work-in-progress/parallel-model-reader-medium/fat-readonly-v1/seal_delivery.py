import pathlib, hashlib, json, datetime
R = pathlib.Path(__file__).resolve().parent
P = R.parents[2]
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
source = P / 'evidence/usb-storage-inputs-20260910/nuttx/fs/fat'
entries = []
for p in sorted((R / 'input/fat').iterdir()):
    original = source / p.name
    assert original.read_bytes() == p.read_bytes(), str(original)
    entries.append({'path': original.relative_to(P).as_posix(), 'sha256': digest(original)})
for folder in ['usb-storage-vfs-20260910', 'usb-storage-mount-20260910']:
    for p in sorted((P / 'evidence' / folder).rglob('*')):
        if p.is_file():
            entries.append({'path': p.relative_to(P).as_posix(), 'sha256': digest(p)})
p = P / 'evidence/usb-storage-inputs-20260910/inputs.json'
entries.append({'path': p.relative_to(P).as_posix(), 'sha256': digest(p)})
(R / 'evidence/input-hashes.json').write_text(json.dumps(entries, indent=2) + '\n', encoding='utf-8')
patches = [R / 'evidence' / ('patch-' + name + '.diff') for name in ['Kconfig', 'fs_fat32.c', 'fs_fat32util.c', 'fs_fat32dirent.c', 'fs_fat32attrib.c']]
(R / 'fat-force-readonly.patch').write_text(''.join(p.read_text() for p in patches), encoding='utf-8')
files = [{'path': p.relative_to(R).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(R.rglob('*')) if p.is_file() and p.name != 'delivery.json']
delivery = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'scope': 'Unintegrated explicit FAT read-only candidate; selected real C functions with mock block device; no target execution', 'files': files}
(R / 'delivery.json').write_text(json.dumps(delivery, indent=2) + '\n', encoding='utf-8')
for entry in files:
    assert digest(R / entry['path']) == entry['sha256']
print('delivery.json SHA256', digest(R / 'delivery.json'), 'files', len(files))
