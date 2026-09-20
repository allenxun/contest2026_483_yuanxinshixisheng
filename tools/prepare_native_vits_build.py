"""Prepare the bounded two-job native VITS candidate build."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/build_native_sherpa_asr3.py').read_text().replace('native-sherpa-asr-build3','native-vits-build1').replace('native-sherpa-config2-20260911','native-vits-lexicon-20260911').replace('compile-attempt3','compile-attempt1').replace("'-j4'","'-j2'")
p=R/'tools/build_native_vits1.py';assert not p.exists();p.write_text(s)
