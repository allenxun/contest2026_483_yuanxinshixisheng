"""Revision-specific guards and RAM tools; no device action."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def create(name,s):
 with (R/'tools'/name).open('x',encoding='utf-8',newline='\n') as f:f.write(s)
s=(R/'tools/verify_graph_core_image.py').read_text().replace('graph-core-20260910','arena-provider-20260910')
s=s.replace("['CONFIG_EXAMPLES_K7GRAPH=y'", "['CONFIG_EXAMPLES_K7ARENA=y','CONFIG_EXAMPLES_K7GRAPH=y'")
create('verify_arena_provider_image.py',s)
s=(R/'tools/uart_load_graph_core.py').read_text().replace('verify_graph_core_image','verify_arena_provider_image').replace('graph-core-20260910','arena-provider-20260910').replace('neon-file64-20260910','graph-core-20260910')
create('uart_load_arena_provider.py',s)
s=(R/'tools/reboot_graph_core_ram.py').read_text().replace('verify_graph_core_image','verify_arena_provider_image').replace('graph-core-20260910','arena-provider-20260910')
create('reboot_arena_provider_ram.py',s)
for old,new in [('check_graph_core_affinity.py','check_arena_provider_affinity.py'),('start_graph_core_radio.py','start_arena_provider_radio.py')]:
 s=(R/'tools'/old).read_text().replace('graph-core-20260910','arena-provider-20260910')
 s=s.replace('console_baud(R, E.name)',"1500000")
 create(new,s)
print('New arena guards/tools prepared')
