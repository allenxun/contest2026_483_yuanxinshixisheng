"""Prepare same-scope wireless checks for the newly linked diagnostic image."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for src,dst in [('check_voice_owner_affinity.py','check_voice_ort_affinity.py'),('start_voice_owner_radio.py','start_voice_ort_radio.py')]:
 s=(R/'tools'/src).read_text().replace('voice-owner-20260910','voice-ort-add-20260911').replace('verify_voice_owner_image','verify_voice_ort_add_image')
 p=R/'tools'/dst;assert not p.exists();p.write_text(s)
