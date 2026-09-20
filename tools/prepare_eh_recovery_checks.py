"""Prepare new evidence destinations for recovery, preserving earlier success."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for name in ['check_neon_file64_affinity.py','start_neon_file64_radio.py']:
    out=R/'tools'/name.replace('neon_file64','eh_recovery');assert not out.exists()
    s=(R/'tools'/name).read_text().replace("'evidence/neon-file64-20260910'", "'evidence/cxx-eh-20260910/recovery'")
    s=s.replace('ramload-resume-progress.txt','ramload-progress.txt')
    s=s.replace('console_baud(R, E.name)',"console_baud(R, 'neon-file64-20260910')")
    out.write_text(s,newline='\n')
p=R/'project-manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
m['current_device']=dict(running_revision=None,state='Restoring neon-file64 after failed cxx-eh cold probe',
 wifi_connected=None,ble_service_running=None,evidence_directory='evidence/cxx-eh-20260910/recovery')
m['pending_firmware']=dict(revision='graph-core-20260910',compiled=True,hardware_tested=False,
 blocker='C++ two-worker cold throw aborted; exact runtime diagnosis in progress')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Recovery destinations prepared; current runtime remains unconfirmed until checks')
