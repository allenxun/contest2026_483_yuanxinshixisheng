"""Freeze a diagnostic loader derived from the proven owner CRC loader."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
for source,target in [('uart_load_voice_owner.py','uart_load_voice_ort_add.py'),('reboot_voice_owner_ram.py','reboot_voice_ort_add_ram.py')]:
 text=(R/'tools'/source).read_text()
 text=text.replace('from verify_voice_owner_image import verify','from verify_voice_ort_add_image import verify')
 text=text.replace("'voice-owner-20260910'","'voice-ort-add-20260911'")
 if source.startswith('reboot'):
  text=text.replace('artifacts/voice-owner-20260910','artifacts/voice-ort-add-20260911')
  text=text.replace('evidence/voice-owner-20260910','evidence/voice-ort-add-20260911')
 if source.startswith('uart'):
  text=text.replace("'voice-cold-20260910'","'voice-owner-20260910'")
  text=text.replace('evidence/build/voice-cold-20260910/verification.json','evidence/build/voice-owner-20260910/verification.json')
  text=text.replace('0 < len(payload) < 0x800000','0 < len(payload) < result[\'memory_bytes\']')
  # Index exact old chunks once. Avoid repeatedly searching a multi-MiB snapshot.
  begin=text.index('reuse = {offset:')
  end=text.index('\nbase = ',begin)
  text=text[:begin]+"previous_chunks = {previous[p:p+4096]: p for p in range(0,len(previous),4096)}\nreuse = {p: previous_chunks.get(payload[p:p+4096], -1) for p in range(0,len(payload),4096)}"+text[end:]
 out=R/'tools'/target
 assert not out.exists()
 out.write_text(text,encoding='utf-8',newline='\n')
