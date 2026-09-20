from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/audit_native_sherpa_link1.py').read_text().replace('native-sherpa-link1','native-sherpa-link2').replace('/link1','/link2').replace('compile-attempt2','compile-attempt3').replace('audit-sherpa-capi.py','audit-sherpa-capi2.py')
p=R/'tools/audit_native_sherpa_link2.py';assert not p.exists();p.write_text(s)
