"""Reuse pinned build compile flags; emit candidate objects only in /tmp."""
import base64
from cloud_radio_stage_audit import ROOT, remote

files = list((ROOT/'app/k7host').glob('*.h'))
files += [ROOT/'app/gimbal/gimbal_link.h']
files += [ROOT/'app/k7host'/name for name in ('k7host_main.c','k7_pipeline.c','k7_track.c')]
targets=['app/k7host/'+name for name in ('k7host_main.c','k7_pipeline.c','k7_track.c')]
targets+=['app/k7agent/cloud/src/k7cloud_main.c','app/k7agent/cloud/src/board_speech_bridge.c']
targets+=['app/k7sound/pio.c','app/k7sound/k7sound_main.c']
targets+=['app/k7host/k7_photo.c','app/k7host/k7_photo_store.c']
files += [ROOT/name for name in targets[3:]]
files += list((ROOT/'app/k7sound').rglob('*.h'))
files += list((ROOT/'app/k7sound').glob('*.inc'))
files += [ROOT/'app/k7agent/cloud/src/board_voice_prompts.inc']
files += [ROOT/'app/k7agent/cloud/include/device_voice_intent.h']
files += [ROOT/'app/k7agent/cloud/include/device_photo_prompts.h']
payload = {p.relative_to(ROOT).as_posix():base64.b64encode(p.read_bytes()).decode() for p in files}
code = '''import pathlib,json,base64,shlex,subprocess,tempfile
build=pathlib.Path('/home/swl/openvela/cmake_out/velavision_tts_max_20260915')
commands=json.loads((build/'compile_commands.json').read_text())
with tempfile.TemporaryDirectory(prefix='k7-voice-arm64-') as folder:
 root=pathlib.Path(folder)
 for rel,encoded in %r.items():
  path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base64.b64decode(encoded))
 for rel in %r:
  name=pathlib.Path(rel).name
  compile_rel=rel.replace('k7_photo_store.c','k7_photo.c')
  entries=[entry for entry in commands if entry['file'].endswith('/'+compile_rel[4:])]
  assert len(entries)==1,(name,len(entries))
  entry=entries[0];args=shlex.split(entry['command'])
  args=[str(root/rel) if arg==entry['file'] else arg for arg in args]
  assert str(root/rel) in args
  output=args.index('-o')+1;args[output]=str(root/(name+'.o'))
  if '-MF' in args:args[args.index('-MF')+1]=str(root/(name+'.d'))
  args += ['-I'+str(root/'app/k7host')]
  args += ['-I'+str(root/'app/k7agent/cloud/include')]
  subprocess.run(args,cwd=entry['directory'],check=True)
  print('ARM64 compile PASS:',name)
print('Candidate objects only; no SDK source or running firmware changed')
''' % (payload,targets)
print(remote(code).decode())
