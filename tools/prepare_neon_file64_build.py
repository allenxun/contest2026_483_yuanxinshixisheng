"""Enable verified NuttX 64-bit file offsets in a distinct SIMD candidate."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'board/kickpi_k7/configs/velavision_neon_file64_local/defconfig'
assert not p.exists()
s=(R/'board/kickpi_k7/configs/velavision_neon_gate_local/defconfig').read_text()
assert '# CONFIG_FS_LARGEFILE is not set' in s
p.parent.mkdir(parents=True)
p.write_text(s.replace('# CONFIG_FS_LARGEFILE is not set','CONFIG_FS_LARGEFILE=y'),newline='\n')
for source,target in [('build_neon_gate.sh','build_neon_file64.sh'),('build_neon_gate_vm.py','build_neon_file64_vm.py')]:
    s=(R/'tools'/source).read_text().replace('neon-gate','neon-file64').replace('neon_gate','neon_file64')
    s=s.replace("['CONFIG_EXAMPLES_K7NEON=y',", "['CONFIG_FS_LARGEFILE=y','CONFIG_EXAMPLES_K7NEON=y',")
    (R/'tools'/target).write_text(s,newline='\n')
