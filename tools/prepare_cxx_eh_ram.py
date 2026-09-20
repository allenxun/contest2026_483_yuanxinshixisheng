"""Generate version-specific RAM tools; retain prior immutable evidence."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for name in ['verify_neon_file64_image.py','reboot_neon_file64_ram.py','uart_load_neon_file64.py',
             'check_neon_file64_affinity.py','start_neon_file64_radio.py']:
    out=R/'tools'/name.replace('neon_file64','cxx_eh');assert not out.exists()
    s=(R/'tools'/name).read_text().replace('neon-file64-20260910','cxx-eh-20260910').replace('neon_file64','cxx_eh')
    s=s.replace('ramload-resume-progress.txt','ramload-progress.txt')
    if name.startswith('verify_'):
        s=s.replace("['CONFIG_FS_LARGEFILE=y',", "['CONFIG_EXAMPLES_K7EH=y','CONFIG_CXX_WCHAR=y','CONFIG_CXX_MINI_LOCALIZATION=y','CONFIG_FS_LARGEFILE=y',")
    if name.startswith('uart_'):
        s=s.replace('cxx-unwind-20260910','neon-file64-20260910')
    if name.startswith('reboot_'):
        s=s.replace("out=R/'evidence/cxx-eh-20260910';out.mkdir(exist_ok=True)",
            "import argparse\np=argparse.ArgumentParser();p.add_argument('--label',choices=['cold','warm'],required=True);a=p.parse_args()\nout=R/'evidence/cxx-eh-20260910'/a.label;out.mkdir(exist_ok=True)")
    out.write_text(s,newline='\n')
print('Generated cxx-eh RAM tools')
