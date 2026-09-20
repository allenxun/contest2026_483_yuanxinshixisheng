from pathlib import Path
p=Path(__file__).parent
q=p/'make_patch.py';s=q.read_text();anchor="(p/'env-gate.cc').write_text(s)"
extra='''s=s.replace('      while (nanosleep(&sleep_time, &sleep_time) != 0 && errno == EINTR) {\\n        // Ignore signals and wait for the full interval to elapse.\\n      }', '''+"'''"+'''#if defined(ORT_K7_NUTTX)
      while (nanosleep(&sleep_time, &sleep_time) != 0) {
        if (errno != EINTR) ORT_THROW("K7 nanosleep failed: ", errno);
      }
#else
      while (nanosleep(&sleep_time, &sleep_time) != 0 && errno == EINTR) {
        // Ignore signals and wait for the full interval to elapse.
      }
#endif'''+"'''"+''')
'''
assert anchor in s;s=s.replace(anchor,extra+anchor);q.write_text(s)
q=p/'model_reader.h';q.write_bytes(Path('E:/openvela/VelaVision/app/k7agent/model_reader/model_reader.h').read_bytes())
(p/'model_reader.c').write_bytes((p/'input/06-model_reader.c').read_bytes())
