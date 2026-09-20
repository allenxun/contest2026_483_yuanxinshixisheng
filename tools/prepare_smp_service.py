"""Create a separate build-only SMP service profile; never touch the board."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
profile = R / 'board/kickpi_k7/configs/velavision_smp_service_local/defconfig'
assert not profile.exists()
text = (R / 'board/kickpi_k7/configs/velavision_emmc_vfs_local/defconfig').read_text()
text = text.replace('CONFIG_UP=y', '# CONFIG_UP is not set').replace('CONFIG_SMP_NCPUS=1\n', 'CONFIG_SMP_NCPUS=8\n')
text = text.replace('CONFIG_NCPUS=1\n', 'CONFIG_NCPUS=8\n')
text += '\n# Experimental integration: default services inherit CPU0; compute workers opt in.\nCONFIG_RK3576_SMP_DIAG=y\nCONFIG_SMP=y\nCONFIG_SMP_DEFAULT_CPUSET=0x1\nCONFIG_EXAMPLES_K7SMP=y\n'
profile.parent.mkdir(parents=True)
profile.write_text(text, encoding='utf-8', newline='\n')
for src, dst in [('build_smp_eight.sh', 'build_smp_service.sh'), ('build_smp_eight_vm.py', 'build_smp_service_vm.py')]:
    text = (R / 'tools' / src).read_text()
    text = text.replace('smp-eight', 'smp-service').replace('smp_eight', 'smp_service')
    if dst.endswith('_vm.py'):
        text = text.replace("'CONFIG_BOARDCTL_RESET=y'])", "'CONFIG_BOARDCTL_RESET=y','CONFIG_SMP_DEFAULT_CPUSET=0x1','CONFIG_EXAMPLES_K7RADIO_IP=y','CONFIG_BCH_DEVICE_READONLY=y'])")
    (R / 'tools' / dst).write_text(text, encoding='utf-8', newline='\n')
# Unchanged project inputs must match their current canonical hash in the mirror.
# The VM script refuses unknown mirror and SDK edits before applying anything.
old = {}
for subtree in ['app', 'port', 'board']:
    for p in (R / subtree).rglob('*'):
        if p.is_file():
            old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
for p in [R / 'tools/sync_sdk.py', R / 'evidence/sync/smp-diag-baseline.json']:
    old[p.relative_to(R).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
(R / 'private/smp-service-original-hashes.json').write_text(json.dumps(old))
print('Prepared experimental eight-core service build; no hardware operations')
