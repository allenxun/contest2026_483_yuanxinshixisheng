from pathlib import Path
import json,hashlib,shutil
here=Path(__file__).resolve().parent
root=here.parents[1]
files=['app/k7sound/'+n for n in ('k7sound_main.c','k7sound_api.h','pio.c','pio.h')]
files+=['app/voicelink/'+n for n in ('CMakeLists.txt','Kconfig','src/core.cpp','src/parsers.cpp','src/k7voice_main.cpp','src/native_speech_output.hpp','src/tts_assets.hpp','include/voicelink/tts_runtime.h','include/voicelink/speech_pcm.hpp')]
files+=['port/new/nuttx/include/nuttx/mm/k7_model_arena.h','port/new/nuttx/arch/arm64/src/rk3576/rk3576_boot.c']
files += [p.relative_to(root).as_posix() for p in (root/'board/kickpi_k7/configs/velavision_spoken_tts_local').rglob('*') if p.is_file()]
manifest={}
for name in files:
    target=here/'input'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/name,target)
    manifest[name]=hashlib.sha256(target.read_bytes()).hexdigest()
(here/'inputs.json').write_text(json.dumps(manifest,indent=2))
