import json, shlex, subprocess, hashlib
from pathlib import Path
here=Path(__file__).resolve().parent
build=Path('/home/swl/openvela/cmake_out/velavision_voice_ui_connect_20260913')
commands=json.loads((build/'compile_commands.json').read_text())
results=[]
for name in ('k7sound_main.c','pio.c','k7voice_main.cpp','core.cpp'):
    matches=[v for v in commands if Path(v['file']).name==name and ('k7sound' in v['file'] or 'voicelink' in v['file'])]
    assert len(matches)==1, (name,len(matches))
    item=matches[0]
    cmd=shlex.split(item['command'])
    source=here/name
    original=cmd[cmd.index('-c')+1]
    cmd[cmd.index('-c')+1]=str(source)
    cmd[cmd.index('-o')+1]=str(here/(name+'.o'))
    cmd[1:1]=['-I'+str(here),'-I'+str(here/'include'),'-I'+str(Path(original).parent)]
    if name=='k7voice_main.cpp': cmd.append('-DK7VOICE_NATIVE_TTS=1')
    result=subprocess.run(cmd,cwd=item['directory'],capture_output=True,timeout=180)
    (here/(name+'.log')).write_bytes(result.stdout+result.stderr)
    results.append({'name':name,'exit_code':result.returncode,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'command':cmd})
    if result.returncode: print(result.stderr.decode(errors='replace')[-5000:])
(here/'compile-result.json').write_text(json.dumps(results,indent=2))
assert all(r['exit_code']==0 for r in results)
print('PASS four ARM64 objects; no final link or board deployment')
