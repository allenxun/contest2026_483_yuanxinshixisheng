"""Integrate frozen exception probe into a distinct, non-default firmware."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-cxx-unwind-medium/concurrent-probe-v1'
raw=(C/'k7eh_main.cxx').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='667527d784ab9a80a7bc880a0c0d32818c051bc55c9949592edfec1bd6085536'
app=R/'app/k7eh';assert not app.exists();app.mkdir()
(app/'k7eh_main.cxx').write_bytes(raw)
for name in ['Kconfig','CMakeLists.txt','Make.defs','Makefile']:
    s=(R/'app/k7cxx'/name).read_text().replace('K7CXX','K7EH').replace('k7cxx','k7eh')
    s=s.replace('K7 native C++ runtime prerequisite probe','K7 two-worker exception diagnostic')
    if name=='Kconfig':s=s.replace('depends on HAVE_CXX','depends on SMP && HAVE_CXX')
    (app/name).write_text(s,newline='\n')
profile=R/'board/kickpi_k7/configs/velavision_cxx_eh_local/defconfig'
assert not profile.exists();profile.parent.mkdir(parents=True)
s=(R/'board/kickpi_k7/configs/velavision_cxx_locale_local/defconfig').read_text()
profile.write_text(s+'\nCONFIG_EXAMPLES_K7EH=y\n',newline='\n')
for name in ['build_cxx_locale.sh','build_cxx_locale_vm.py']:
    s=(R/'tools'/name).read_text().replace('cxx-locale','cxx-eh').replace('cxx_locale','cxx_eh')
    if name.endswith('_vm.py'):
        s=s.replace('paths=list(dict.fromkeys(paths))',
          "paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7eh').iterdir()) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
        s=s.replace("['CONFIG_CXX_WCHAR=y',", "['CONFIG_EXAMPLES_K7EH=y','CONFIG_CXX_WCHAR=y',")
    (R/'tools'/name.replace('cxx_locale','cxx_eh')).write_text(s,newline='\n')
out=R/'evidence/cxx-eh-20260910';out.mkdir()
(out/'integration.json').write_text(json.dumps(dict(source=str(C/'k7eh_main.cxx'),
 sha256=hashlib.sha256(raw).hexdigest(),target='app/k7eh/k7eh_main.cxx',
 scope='Unmodified candidate; explicit command only; each cold/warm attempt needs fresh boot'),indent=2)+'\n')
print('Prepared cxx-eh independent candidate')
