from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=R/'tools/audit_native_session_link.py'
s=p.read_text().replace('native-session-link1','native-session-link2').replace('link-attempt1','link-attempt2')
s=s.replace("archives.append(S/'config-attempt9/libk7_iconv.a')","archives.append(S/'config-attempt9/libk7_iconv.a')\narchives.append(S/'support-attempt1/libk7_locale.a')")
(R/'tools/audit_native_session_link2.py').write_text(s)
