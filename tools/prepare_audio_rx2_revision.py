"""Prepare independent RX lane diagnostic without mixing radio changes."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
old=json.loads((R/'private/audio-mmu-original-hashes.json').read_text())
for rel in list(old):
 p=R/rel
 if p.is_file():old[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
for p in list((R/'app/k7sound').rglob('*'))+[R/'tools/build_audio_mmu.sh',R/'tools/sync_sdk.py']:
 if p.is_file():old[p.relative_to(R).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
dest=R/'private/audio-rx2-original-hashes.json';assert not dest.exists()
dest.write_text(json.dumps(old))
for name in ['build_audio_mmu_vm.py','build_audio_mmu.sh','verify_audio_mmu_image.py','reboot_audio_mmu_ram.py','uart_load_audio_mmu.py','check_audio_mmu_affinity.py','start_audio_mmu_radio.py']:
 s=(R/'tools'/name).read_text().replace('audio-mmu','audio-rx2').replace('audio_mmu','audio_rx2')
 if name=='build_audio_mmu_vm.py':
  marker="paths.append('evidence/build/audio-marker-20260910/verification.json')"
  assert marker in s
  s=s.replace(marker,marker+"\npaths.append('evidence/build/audio-mmu-20260910/verification.json')")
 if name=='uart_load_audio_mmu.py':s=s.replace('audio-marker-20260910','audio-mmu-20260910')
 target=R/'tools'/name.replace('audio_mmu','audio_rx2');assert not target.exists()
 target.write_text(s,encoding='utf-8',newline='\n')
C=R/'work-in-progress/parallel-neon-probe-medium/audio-fifo-next-v1'
want='de66218d99abc3235a644430c9b46a5aa9f64a8ab78f38e33a168f46f600396b'
assert hashlib.sha256((C/'outputs.json').read_bytes()).hexdigest()==want
for row in json.loads((C/'outputs.json').read_text()):assert hashlib.sha256((C/row['path']).read_bytes()).hexdigest()==row['sha256']
for row in json.loads((C/'inputs.json').read_text()):assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256']
for name in ('duplex.c','duplex.h'):(R/'app/k7sound'/name).write_bytes((C/'candidate'/name).read_bytes())
p=R/'app/k7sound/k7sound_main.c';s=p.read_text()
marker='  bool numbered = !strcmp(argv[1], "loopback-numbered");';assert marker in s
s=s.replace(marker,'  bool rx2 = !strcmp(argv[1], "loopback-rx2");\n'+marker)
s=s.replace('bool loopback = numbered ||','bool loopback = rx2 || numbered ||')
s=s.replace('      if (numbered)\n','      if (rx2)\n        rc = dl_run_numbered_rx2(&dl, platform.ready, 1, 4096000, loop_capture, 512, &loop_result);\n      else if (numbered)\n')
marker='      data_held = loop_result.held;';assert marker in s
s=s.replace(marker,marker+'\n      if (rx2) printf("AUDIO RXCSR before=%08x active=%08x restored=%08x restore_rc=%d\\n", loop_result.rxcr_before, loop_result.rxcr_active, loop_result.rxcr_restored, loop_result.rx_restore_rc);')
p.write_text(s,newline='\n')
p=R/'tools/sync_sdk.py';s=p.read_text();assert "'audio-marker-20260910')" in s
s=s.replace("'audio-marker-20260910')","'audio-marker-20260910', 'audio-mmu-20260910')");p.write_text(s,newline='\n')
p=R/'tools/observe_audio_io.py';s=p.read_text()
s=s.replace("'audio-marker-20260910'],","'audio-marker-20260910','audio-rx2-20260910'],")
s=s.replace("'k7sound loopback-numbered'],","'k7sound loopback-numbered','k7sound loopback-rx2'],")
s=s.replace("'audio-marker-20260910':'verify_audio_marker_image'}","'audio-marker-20260910':'verify_audio_marker_image','audio-rx2-20260910':'verify_audio_rx2_image'}")
p.write_text(s,newline='\n')
E=R/'evidence/audio-rx2-20260910';E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256=want,change='RX CSR only: 1 to 2 lanes; numbered default-route muted capture',word_pairs=128,hardware_tested=False),indent=2))
print('RX2 isolated candidate prepared')
