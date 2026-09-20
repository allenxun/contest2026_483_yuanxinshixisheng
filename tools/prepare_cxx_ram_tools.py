"""Derive candidate-specific RAM tools without changing tested prior tools."""
from pathlib import Path
R = Path(__file__).resolve().parents[1]
for name in ['reboot_smp_load_ram.py','uart_load_smp_load.py','check_smp_load_affinity.py','start_smp_load_radio.py']:
    target = R/'tools'/name.replace('smp_load','cxx_tls')
    if target.exists(): raise SystemExit('Tool exists: '+str(target))
    text = (R/'tools'/name).read_text().replace('smp-load-20260910','cxx-tls-20260910').replace('verify_smp_load_image','verify_cxx_tls_image')
    if name == 'uart_load_smp_load.py':
        text = text.replace('smp-service-20260910','smp-load-20260910')
    target.write_text(text, newline='\n')
