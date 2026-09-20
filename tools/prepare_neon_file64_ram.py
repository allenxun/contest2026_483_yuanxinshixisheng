from pathlib import Path
R=Path(__file__).resolve().parents[1]
for source in ['verify_cxx_unwind_image.py','reboot_cxx_unwind_ram.py','uart_load_cxx_unwind.py',
               'check_cxx_unwind_affinity.py','start_cxx_unwind_radio.py','check_cxx_unwind_runtime.py']:
    target=R/'tools'/source.replace('cxx_unwind','neon_file64')
    assert not target.exists()
    s=(R/'tools'/source).read_text().replace('cxx-unwind-20260910','neon-file64-20260910').replace('cxx_unwind','neon_file64')
    if source.startswith('verify_'):
        s=s.replace("['CONFIG_EXAMPLES_K7CXX=y',", "['CONFIG_FS_LARGEFILE=y','CONFIG_EXAMPLES_K7NEON=y','CONFIG_EXAMPLES_K7CXX=y',")
    if source.startswith('uart_'):
        s=s.replace('smp-load-20260910','cxx-unwind-20260910')
    if source.endswith('_runtime.py'):
        s=s.replace("match[1]==b'PASS'", "match[1]==b'PASS' and int(match[3])==64")
    target.write_text(s,newline='\n')
