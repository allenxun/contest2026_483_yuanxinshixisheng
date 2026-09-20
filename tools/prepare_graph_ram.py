"""Use an independently audited 8MiB cap for the graph diagnostic only."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for name in ['verify_neon_file64_image.py','reboot_neon_file64_ram.py','uart_load_neon_file64.py',
             'check_neon_file64_affinity.py','start_neon_file64_radio.py']:
    out=R/'tools'/name.replace('neon_file64','graph_core');assert not out.exists()
    s=(R/'tools'/name).read_text().replace('neon-file64-20260910','graph-core-20260910').replace('neon_file64','graph_core')
    s=s.replace('ramload-resume-progress.txt','ramload-progress.txt')
    if name.startswith('verify_'):
        s=s.replace("['CONFIG_FS_LARGEFILE=y',", "['CONFIG_EXAMPLES_K7GRAPH=y','CONFIG_CXX_WCHAR=y','CONFIG_CXX_MINI_LOCALIZATION=y','CONFIG_FS_LARGEFILE=y',")
        s=s.replace('<= 0x40a00000','<= 0x40c00000')
        needle="    binary = (build/'nuttx.bin').read_bytes()"
        s=s.replace(needle,"    layout=json.loads((ROOT/'evidence/build'/REV/'layout-audit.json').read_text())\n    assert layout['layout_passed'] and layout['sha256']==report['artifacts']['nuttx']['sha256']\n    assert int(layout['memory_end'],16)<=0x40c00000\n"+needle)
    if name.startswith('uart_'):s=s.replace('cxx-unwind-20260910','neon-file64-20260910')
    out.write_text(s,newline='\n')
print('Graph-only 8MiB cap plus source/artifact/bin/ELF/layout/unwind gates retained')
