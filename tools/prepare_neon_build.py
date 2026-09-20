"""Compile the independently reviewed SIMD gate after the C++ runtime fix."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'board/kickpi_k7/configs/velavision_neon_gate_local/defconfig'
assert not p.exists()
p.parent.mkdir(parents=True)
p.write_text((R/'board/kickpi_k7/configs/velavision_cxx_unwind_local/defconfig').read_text()+'\nCONFIG_EXAMPLES_K7NEON=y\n',newline='\n')
extra=[str(p.relative_to(R)).replace('\\','/') for root in ['app/k7neon','app/k7agent'] for p in sorted((R/root).rglob('*')) if p.is_file()]
for source,target in [('build_cxx_unwind.sh','build_neon_gate.sh'),('build_cxx_unwind_vm.py','build_neon_gate_vm.py')]:
    s=(R/'tools'/source).read_text().replace('cxx-unwind','neon-gate').replace('cxx_unwind','neon_gate')
    s=s.replace('private/neon-gate-original-hashes.json','private/cxx-unwind-original-hashes.json')
    s=s.replace('evidence/sync/neon-gate-baseline.json','evidence/sync/cxx-unwind-baseline.json')
    if target.endswith('.py'):
        s=s.replace('paths=list(dict.fromkeys(paths))','paths += '+repr(extra)+'\npaths=list(dict.fromkeys(paths))')
        s=s.replace("['CONFIG_EXAMPLES_K7CXX=y',", "['CONFIG_EXAMPLES_K7NEON=y','CONFIG_EXAMPLES_K7CXX=y',")
    (R/'tools'/target).write_text(s,newline='\n')
