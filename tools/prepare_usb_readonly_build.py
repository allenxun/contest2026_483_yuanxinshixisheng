"""Stage reviewed MSC v2; preserve exact pre-change hashes for SDK audit."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R/'work-in-progress/parallel-cxx-unwind-medium/usb-msc-checked-v2'
E = R/'evidence/usb-readonly-20260910'
E.mkdir(exist_ok=True)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(C/'delivery.json') == '8c3fc8cdb96bea9fc20bb932f995af210e0f48bc3790c7264441b69c423d842b'
delivery = json.loads((C/'delivery.json').read_text())
for row in delivery['files']:
    assert sha(R/row['path']) == row['sha256'], row['path']
changes = {}
for name in ('Kconfig', 'usbhost_storage.c'):
    source = C/'candidate/drivers/usbhost'/name
    frozen = R/'evidence/usb-storage-inputs-20260910/nuttx/drivers/usbhost'/name
    target = R/'port/tracked/nuttx/drivers/usbhost'/name
    assert not target.exists() or sha(target) == sha(frozen), str(target)
    changes[target.relative_to(R).as_posix()] = dict(old=sha(frozen), new=sha(source))
    target.write_bytes(source.read_bytes())
p = R/'port/new/nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c'
old = sha(p)
s = p.read_text()
needle = '  g_connection = xhci_initialize("k7-usb-a", 0, HOST, &g_ops, NULL);'
assert s.count(needle) == 1
s = s.replace(needle, '#ifdef CONFIG_USBHOST_MSC\n  ret = usbhost_msc_initialize();\n  if (ret < 0) goto out;\n#endif\n'+needle)
p.write_text(s, newline='\n')
changes[p.relative_to(R).as_posix()] = dict(old=old, new=sha(p))
profile = R/'board/kickpi_k7/configs/velavision_usb_readonly_local/defconfig'
profile.parent.mkdir()
profile.write_text((R/'board/kickpi_k7/configs/velavision_arena_provider_local/defconfig').read_text()+
    '\nCONFIG_USBHOST_MSC=y\nCONFIG_USBHOST_MSC_READONLY=y\nCONFIG_EXAMPLES_K7STORAGE=y\n# CONFIG_FS_FAT is not set\n', newline='\n')
(E/'integration.json').write_text(json.dumps(dict(candidate_delivery_sha256=sha(C/'delivery.json'),
    files=changes, scope='MSC only; FAT disabled; hardware not yet tested'), indent=2)+'\n')
# Local staging mirror must still match either the recorded predecessor or new bytes.
baseline = json.loads((R/'private/cxx-unwind-original-hashes.json').read_text(encoding='utf-8-sig'))
baseline.update({k:v['old'] for k,v in changes.items()})
(R/'private/usb-readonly-original-hashes.json').write_text(json.dumps(baseline, indent=2)+'\n')
for name in ('build_arena_provider.sh', 'build_arena_provider_vm.py'):
    s = (R/'tools'/name).read_text().replace('arena-provider', 'usb-readonly').replace('arena_provider', 'usb_readonly')
    if name.endswith('_vm.py'):
        s = s.replace('private/cxx-unwind-original-hashes.json', 'private/usb-readonly-original-hashes.json')
        extra = list(changes)
        extra += [str(p.relative_to(R)).replace('\\','/') for p in sorted((R/'app/k7storage').iterdir()) if p.is_file()]
        s = s.replace('paths=list(dict.fromkeys(paths))', 'paths += '+repr(extra)+'\npaths=list(dict.fromkeys(paths))')
        s = s.replace("['CONFIG_EXAMPLES_K7ARENA=y',", "['CONFIG_USBHOST_MSC=y','CONFIG_USBHOST_MSC_READONLY=y','CONFIG_EXAMPLES_K7STORAGE=y','CONFIG_EXAMPLES_K7ARENA=y',")
        s = s.replace("report=dict(revision=", "assert 'CONFIG_FS_FAT=y' not in (B/'.config').read_text().splitlines()\nreport=dict(revision=")
    dest = R/'tools'/name.replace('arena_provider','usb_readonly')
    assert not dest.exists()
    dest.write_text(s, newline='\n')
print('MSC-only candidate staged; no device access')
