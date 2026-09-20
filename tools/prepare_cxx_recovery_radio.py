from pathlib import Path
R=Path(__file__).resolve().parents[1]
for name,target in [('check_smp_load_affinity.py','check_cxx_recovery_affinity.py'),('start_smp_load_radio.py','start_cxx_recovery_radio.py')]:
    s=(R/'tools'/name).read_text().replace("E = R / 'evidence/smp-load-20260910'", "E = R / 'evidence/cxx-tls-20260910'")
    s=s.replace("E=R/'evidence/smp-load-20260910'", "E=R/'evidence/cxx-tls-20260910'")
    s=s.replace('ramload-progress.txt','recovery-progress.txt').replace('affinity-boot','recovery-affinity-boot').replace('affinity-radio','recovery-affinity-radio')
    s=s.replace('console_baud(R, E.name)', "console_baud(R, 'smp-load-20260910')")
    s=s.replace("(E/(name+'.bin'))", "(E/('recovery-'+name+'.bin'))")
    (R/'tools'/target).write_text(s,newline='\n')
