"""Prepare isolated exact-source no-pipe integration and incremental ASR build."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/apply_native_kiss_patch.py').read_text()
s=s.replace('native-kiss-patch','native-pipe-patch').replace('native-kissfft-log-macro-v1/candidate/kiss_fft_log.h','native-kaldifst-no-pipe-v1/kaldi-io.cc')
s=s.replace('c64bd308e46162c63c15e842174de29ba1e9326a95278e3cc77b55d3bc3ce693','461f5b15450ef30f1c4253b89b009a6f79361000e4e5bf2aa46963eed7a6c24a')
s=s.replace('f954cb6890ec999f7fbc80cdd1c8c0194bbaeb0f1c27e11bd23450f53871cf8c','b87dae3202f3a7e8d4b576f10d1b7ea74da9fa236c7a581f4ffe067331222cc2')
s=s.replace('/dev/shm/velavision-sherpa-asr-20260911/sources/kissfft/kiss_fft_log.h','/home/swl/openvela/work/native-sherpa-config2-20260911/sources/kaldifst/kaldifst/csrc/kaldi-io.cc')
s=s.replace('kiss-patch','pipe-patch').replace('kiss_fft_log.candidate.h','kaldi-io.candidate.cc').replace('apply-kiss.py','apply-pipe.py')
s=s.replace('build_native_sherpa_asr1.py','build_native_sherpa_asr2.py')
s=s.replace("'native-sherpa-asr-build1','native-sherpa-asr-build2'","'native-sherpa-asr-build2','native-sherpa-asr-build3'")
s=s.replace("'compile-attempt1','compile-attempt2'","'compile-attempt2','compile-attempt3'")
s=s.replace("(R/'tools/build_native_sherpa_asr2.py').write_text(s)","(R/'tools/build_native_sherpa_asr3.py').write_text(s)")
p=R/'tools/apply_native_pipe_patch.py';assert not p.exists();p.write_text(s)
