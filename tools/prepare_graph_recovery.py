"""Prepare known graph baseline recovery; original snapshot remains immutable."""
from pathlib import Path
R=Path(__file__).resolve().parents[1];E=R/'evidence/eh-control-20260910/recovery';E.mkdir(exist_ok=True)
def create(name,s):
 with (R/'tools'/name).open('x',encoding='utf-8',newline='\n') as f:f.write(s)
s=(R/'tools/uart_load_graph_core.py').read_text().replace('neon-file64-20260910','graph-core-20260910')
create('uart_recover_graph_core.py',s)
s=(R/'tools/reboot_graph_core_ram.py').read_text().replace("out=R/'evidence/graph-core-20260910'", "out=R/'evidence/eh-control-20260910/recovery'")
create('reboot_graph_recovery.py',s)
for old,new in [('check_graph_core_affinity.py','check_graph_recovery_affinity.py'),('start_graph_core_radio.py','start_graph_recovery_radio.py')]:
 s=(R/'tools'/old).read_text().replace("'evidence/graph-core-20260910'", "'evidence/eh-control-20260910/recovery'")
 s=s.replace('console_baud(R, E.name)', "console_baud(R, 'graph-core-20260910')")
 create(new,s)
print('Preserved-snapshot recovery tools ready')
