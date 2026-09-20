"""Freeze current RX2 inputs and prepare independent pair-readiness build tools."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-rx2-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_rx2.sh',R/'tools/sync_sdk.py']:
 if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
dest=R/'private/audio-guard-original-hashes.json';assert not dest.exists()
dest.write_text(json.dumps(old))
for name in ['build_audio_rx2_vm.py','build_audio_rx2.sh','verify_audio_rx2_image.py','reboot_audio_rx2_ram.py','uart_load_audio_rx2.py','check_audio_rx2_affinity.py','start_audio_rx2_radio.py']:
 s=(R/'tools'/name).read_text().replace('audio-rx2','audio-guard').replace('audio_rx2','audio_guard')
 if name=='build_audio_rx2_vm.py':
  marker="paths.append('evidence/build/audio-mmu-20260910/verification.json')"
  assert marker in s
  s=s.replace(marker,marker+"\npaths.append('evidence/build/audio-rx2-20260910/verification.json')")
 if name=='uart_load_audio_rx2.py':s=s.replace('audio-mmu-20260910','audio-rx2-20260910')
 target=R/'tools'/name.replace('audio_rx2','audio_guard');assert not target.exists()
 target.write_text(s,encoding='utf-8',newline='\n')
print('Guard build tools prepared; formal audio unchanged')
