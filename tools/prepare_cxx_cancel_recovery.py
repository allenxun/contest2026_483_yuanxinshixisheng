"""Restore tested smp-load using the preserved pre-load RAM snapshot."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'tools/recover_cxx_cancel.py'
assert not p.exists()
s=(R/'tools/uart_load_smp_load.py').read_text()
s=s.replace('smp-service-20260910','smp-load-20260910')
s=s.replace("    command(f'cp.b 40400000 {snapshot_base:x} {len(previous):x}')", "    # Preserve original snapshot: destination currently contains a partial candidate.")
s=s.replace("    # A short read avoids", "    s.write(b'\\x03\\r'); s.flush(); time.sleep(.2); s.read(8192)\n    # A short read avoids")
p.write_text(s,newline='\n')
