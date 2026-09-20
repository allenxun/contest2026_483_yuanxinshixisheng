"""Derive revision-specific immutable guards and RAM-only loader, no execution."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def create(name,s):
 p=R/'tools'/name
 with p.open('x',encoding='utf-8',newline='\n') as f:f.write(s)
s=(R/'tools/verify_cxx_eh_image.py').read_text().replace('cxx-eh-20260910','eh-control-20260910')
s=s.replace("['CONFIG_EXAMPLES_K7EH=y'", "['CONFIG_EXAMPLES_K7EHCONTROL=y','CONFIG_EXAMPLES_K7EH=y'")
create('verify_eh_control_image.py',s)
s=(R/'tools/uart_load_graph_core.py').read_text()
s=s.replace('verify_graph_core_image','verify_eh_control_image').replace('graph-core-20260910','eh-control-20260910')
s=s.replace('neon-file64-20260910','graph-core-20260910').replace('len(payload) < 0x800000','len(payload) < 0x600000')
create('uart_load_eh_control.py',s)
s=(R/'tools/reboot_graph_core_ram.py').read_text().replace('verify_graph_core_image','verify_eh_control_image').replace('graph-core-20260910','eh-control-20260910')
create('reboot_eh_control_ram.py',s)
print('Control guards and RAM tools prepared; no hardware action')
