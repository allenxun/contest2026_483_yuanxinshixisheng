"""Restore last accepted neon image from preserved pre-experiment snapshot."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'tools/uart_recover_eh_baseline.py';assert not p.exists()
s=(R/'tools/uart_load_neon_file64.py').read_text().replace('cxx-unwind-20260910','neon-file64-20260910')
s=s.replace('a = p.parse_args()',"a = p.parse_args()\nassert a.resume_preserved_snapshot, 'Recovery must not overwrite preserved baseline snapshot'")
p.write_text(s,newline='\n')
print('Prepared baseline recovery with immutable image and per-block CRC')
