"""Preserve the first candidate and add required task-local C++ storage."""
from pathlib import Path
R = Path(__file__).resolve().parents[1]
p = R/'board/kickpi_k7/configs/velavision_cxx_tls_local/defconfig'
if p.exists(): raise SystemExit('Already prepared')
base = (R/'board/kickpi_k7/configs/velavision_cxx_probe_local/defconfig').read_text()
assert 'CONFIG_TLS_TASK_NELEM=0' in base
p.parent.mkdir(parents=True)
p.write_text(base.replace('CONFIG_TLS_TASK_NELEM=0','CONFIG_TLS_TASK_NELEM=8'), newline='\n')
for source, dest in [('build_cxx_probe.sh','build_cxx_tls.sh'),('build_cxx_probe_vm.py','build_cxx_tls_vm.py')]:
    text = (R/'tools'/source).read_text().replace('cxx-probe','cxx-tls').replace('cxx_probe','cxx_tls')
    text = text.replace("'CONFIG_TLS_NELEM=8',", "'CONFIG_TLS_NELEM=8','CONFIG_TLS_TASK_NELEM=8',")
    (R/'tools'/dest).write_text(text, newline='\n')
