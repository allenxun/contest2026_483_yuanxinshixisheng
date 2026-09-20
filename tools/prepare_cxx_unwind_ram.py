"""Create gated RAM tools for the reviewed unwind-enabled candidate."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
names=['verify_cxx_tls_image.py','reboot_cxx_tls_ram.py','uart_load_cxx_tls.py',
       'check_cxx_tls_affinity.py','start_cxx_tls_radio.py','check_cxx_tls_runtime.py']
for source in names:
    target=R/'tools'/source.replace('cxx_tls','cxx_unwind')
    assert not target.exists(),str(target)
    s=(R/'tools'/source).read_text().replace('cxx-tls-20260910','cxx-unwind-20260910').replace('cxx_tls','cxx_unwind')
    if source.startswith('verify_'):
        s=s.replace("    binary = (build/'nuttx.bin').read_bytes()", "    audit = json.loads((ROOT/'evidence/build'/REV/'unwind-audit.json').read_text())\n    assert audit['passed'] and audit['sha256'] == report['artifacts']['nuttx']['sha256']\n    binary = (build/'nuttx.bin').read_bytes()")
    target.write_text(s,newline='\n')
