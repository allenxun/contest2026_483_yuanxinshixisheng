"""Review-bound silent digital loopback integration, preserving normal PIO."""
import hashlib
import json
from pathlib import Path
R = Path(__file__).resolve().parents[1]
C = R/'work-in-progress/parallel-neon-probe-medium/audio-zero-pattern-v2/duplex-runner'
manifest = C/'outputs.json'
assert hashlib.sha256(manifest.read_bytes()).hexdigest() == '2a3f137b8a122d9e6a5641d1667cda60af3e27546d40e2674bc1d11f55446092'
for row in json.loads(manifest.read_text()):
    assert hashlib.sha256((C/row['name']).read_bytes()).hexdigest() == row['sha256']
for row in json.loads((C/'inputs.json').read_text()):
    assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest() == row['sha256']
for name in ('duplex.c','duplex.h'):
    dst = R/'app/k7sound'/name
    assert not dst.exists()
    dst.write_bytes((C/name).read_bytes())
p = R/'app/k7sound/CMakeLists.txt'
s = p.read_text().replace('playback_filter.c', 'playback_filter.c duplex.c')
p.write_text(s,newline='\n')
p = R/'app/k7sound/k7sound_main.c'
s = p.read_text().replace('#include "playback_filter.h"', '#include "playback_filter.h"\n#include "duplex.h"')
s = s.replace('static unsigned captured_frames;', 'static uint32_t loop_capture[512];\nstatic struct dl_result loop_result;\nstatic unsigned captured_frames;')
s = s.replace('  bool probe =', '  bool loopback = !strcmp(argv[1], "loopback");\n  bool probe =')
s = s.replace('(!probe && !playing && !recording)', '(!probe && !playing && !recording && !loopback)')
marker = '  if (!rc && !probe)\n'
assert marker in s
s = s.replace(marker, '''  if (!rc && loopback)
    {
      /* VERSION/CKR/FSCR/PATH are checked by dl_run for this shared-clock
       * SAI1 profile. Codec stays PREPARED/muted. No amp-enable callback. */
      struct dl_port dl = {NULL, sai_read, sai_write, now_us, amp_off};
      rc = dl_run(&dl, platform.ready, 1, 4096000, loop_capture, 512,
                  128, &loop_result);
      data_held = loop_result.held;
      printf("SOUND loopback result=%d frames=%u tx_queued=%u polls=%u stop=%d restore=%d amp=%d held=%d\\n",
             rc, loop_result.frames, loop_result.tx_words, loop_result.polls,
             loop_result.stop_rc, loop_result.restore_rc, loop_result.amp_rc,
             loop_result.held);
      printf("SOUND loop_path before=%08" PRIx32 " active=%08" PRIx32
             " restored=%08" PRIx32 " start=%" PRIu64 " end=%" PRIu64 "\\n",
             loop_result.path_before, loop_result.path_active,
             loop_result.path_restored, loop_result.start_us, loop_result.end_us);
      for (unsigned direction = 0; direction < 2; direction++)
        {
          unsigned count = direction ? loop_result.nrx : loop_result.ntx;
          const struct dl_word *words = direction ? loop_result.rx : loop_result.tx;
          for (unsigned i = 0; i < count; i++)
            printf("SOUND loop_word dir=%u index=%u us=%" PRIu64
                   " before=%08" PRIx32 " word=%08" PRIx32
                   " after=%08" PRIx32 " rc=%d\\n", direction, i,
                   words[i].us, words[i].before, words[i].word,
                   words[i].after, words[i].rc);
        }
      for (unsigned i = 0; i < loop_result.frames * 2; i += 8)
        {
          printf("LOOP_PCM %04x", i);
          for (unsigned j = i; j < i + 8 && j < loop_result.frames * 2; j++)
            printf(" %08" PRIx32, loop_capture[j]);
          putchar('\\n');
        }
    }
  else if (!rc && !probe)
''')
s = s.replace('int stop_rc = reset_fault ? -EBUSY', 'int stop_rc = (reset_fault || data_held) ? -EBUSY')
marker = '  int platform_rc = '
assert marker in s
s = s.replace(marker, '''  /* A failed/unknown stop must not fall through to restoring gated clocks.
   * Retain the fault until an explicit reset; amplifier force-low remains safe. */
  if (stop_rc || data_held || reset_fault) platform.held = true;
''' + marker)
p.write_text(s,newline='\n')
p = R/'tools/sync_sdk.py'
s = p.read_text().replace("'audio-input-20260910')", "'audio-input-20260910', 'audio-filter-20260910')")
p.write_text(s,newline='\n')
p = R/'tools/observe_audio_io.py'
s = p.read_text().replace("'audio-filter-20260910'],", "'audio-filter-20260910','audio-loopback-20260910'],")
s = s.replace("'k7sound replay-hp-max'],", "'k7sound replay-hp-max','k7sound loopback'],")
s = s.replace("'audio-filter-20260910':'verify_audio_filter_image'}", "'audio-filter-20260910':'verify_audio_filter_image','audio-loopback-20260910':'verify_audio_loopback_image'}")
p.write_text(s,newline='\n')
E = R/'evidence/audio-loopback-20260910'
E.mkdir(exist_ok=True)
(E/'integration.json').write_text(json.dumps(dict(candidate_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    initial_frames=128, amp_enable_callback=False, original_capture_preserved=True,
    failure_blocks_platform_clock_teardown=True, hardware_tested=False),indent=2))
print('Integrated silent 128-frame loopback; compile and device gates pending')
