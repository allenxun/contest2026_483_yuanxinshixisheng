"""Integrate the frozen pure-C playback filter without changing raw capture."""
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
C = R/'work-in-progress/parallel-model-reader-medium/audio-playback-filter-v1'
D = C/'delivery.json'
assert hashlib.sha256(D.read_bytes()).hexdigest() == 'f3b74a4ca44519156435fd288cc3bb900eb574eb8a69c669c2610e726e345b73'
for item in json.loads(D.read_text()):
    assert hashlib.sha256(Path(item['Path']).read_bytes()).hexdigest() == item['Hash'].lower()
for name in ('playback_filter.c', 'playback_filter.h'):
    dst = R/'app/k7sound'/name
    assert not dst.exists()
    dst.write_bytes((C/name).read_bytes())
p = R/'app/k7sound/CMakeLists.txt'
s = p.read_text(); assert 'playback_filter.c' not in s
s = s.replace('k7sound_main.c', 'k7sound_main.c playback_filter.c')
p.write_text(s, newline='\n')
p = R/'app/k7sound/k7sound_main.c'
s = p.read_text()
s = s.replace('#include "start_clear.h"', '#include "start_clear.h"\n#include "playback_filter.h"')
s = s.replace('static uint32_t capture[96000];', 'static uint32_t capture[96000];\nstatic uint32_t filtered_playback[96000];')
s = s.replace('  bool maximum =', '  bool ma4 = !strcmp(argv[1], "replay-ma4-max");\n  bool hp80 = !strcmp(argv[1], "replay-hp-max");\n  bool maximum = ma4 || hp80 ||')
s = s.replace('  bool replay =', '  bool replay = ma4 || hp80 ||')
marker = '  struct saved_i2c old = {0};'
assert marker in s
s = s.replace(marker, '''  const uint32_t *playback_source = capture;
  if (ma4 || hp80)
    {
      uint32_t saturations = 0;
      int filter_rc = af_filter(capture, 96000, filtered_playback, 96000,
                                frames, hp80 ? AF_MA4_HP80 : AF_MA4,
                                &saturations);
      printf("SOUND filter=%u result=%d frames=%u saturations=%u raw_preserved=1\\n",
             hp80 ? 2u : 1u, filter_rc, frames, saturations);
      if (filter_rc) goto invalid;
      playback_source = filtered_playback;
    }
''' + marker)
s = s.replace('pio_play_buffer(&pio, 1, 4096000, capture,', 'pio_play_buffer(&pio, 1, 4096000, playback_source,')
p.write_text(s, newline='\n')
p = R/'tools/sync_sdk.py'
s = p.read_text().replace("'audio-gain-20260910')", "'audio-gain-20260910', 'audio-input-20260910')")
p.write_text(s, newline='\n')
p = R/'tools/observe_audio_io.py'
s = p.read_text().replace("'audio-input-20260910'],", "'audio-input-20260910','audio-filter-20260910'],")
s = s.replace("'k7sound capture-pga24 48000'],", "'k7sound capture-pga24 48000','k7sound replay-ma4-max','k7sound replay-hp-max'],")
s = s.replace("'audio-input-20260910':'verify_audio_input_image'}", "'audio-input-20260910':'verify_audio_input_image','audio-filter-20260910':'verify_audio_filter_image'}")
p.write_text(s, newline='\n')
out = R/'evidence/audio-filter-20260910'; out.mkdir(exist_ok=True)
(out/'integration.json').write_text(json.dumps(dict(candidate_manifest_sha256=hashlib.sha256(D.read_bytes()).hexdigest(), raw_capture_unchanged=True, additional_static_buffer_bytes=384000, hardware_tested=False, audio_quality_accepted=False), indent=2))
p = R/'evidence/audio-input-20260910/runtime-results.json'
d = json.loads(p.read_text()); d['human_feedback'] = '人声更大，但杂声仍明显'; d['clear_voice_accepted'] = False
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print('Frozen filter integrated; build and device verification pending')
