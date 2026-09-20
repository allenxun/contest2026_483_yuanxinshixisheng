"""Stage minimal single-worker/preheated controls without changing old probe."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
C=R/'work-in-progress/parallel-cxx-unwind-medium/eh-control-v1'
data=(C/'k7ehcontrol_main.cxx').read_bytes()
assert hashlib.sha256(data).hexdigest()=='bdf264d28daa30fabfae810616975774123a91ae762e3c740eee8f3fdf6b9652'
A=R/'app/k7ehcontrol';assert not A.exists();A.mkdir()
(A/'k7ehcontrol_main.cxx').write_bytes(data)
for name in ['Kconfig','CMakeLists.txt','Make.defs','Makefile']:
    s=(R/'app/k7eh'/name).read_text().replace('K7EH','K7EHCONTROL').replace('k7eh','k7ehcontrol')
    (A/name).write_text(s,newline='\n')
profile=R/'board/kickpi_k7/configs/velavision_eh_control_local/defconfig'
assert not profile.exists();profile.parent.mkdir(parents=True)
s=(R/'board/kickpi_k7/configs/velavision_cxx_eh_local/defconfig').read_text()
profile.write_text(s+'\nCONFIG_EXAMPLES_K7EHCONTROL=y\n',newline='\n')
for name in ['build_cxx_eh.sh','build_cxx_eh_vm.py']:
    s=(R/'tools'/name).read_text().replace('cxx-eh','eh-control').replace('cxx_eh','eh_control')
    if name.endswith('_vm.py'):
        s=s.replace('paths=list(dict.fromkeys(paths))',"paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7ehcontrol').iterdir()) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
        s=s.replace("['CONFIG_EXAMPLES_K7EH=y',", "['CONFIG_EXAMPLES_K7EHCONTROL=y','CONFIG_EXAMPLES_K7EH=y',")
    (R/'tools'/name.replace('cxx_eh','eh_control')).write_text(s,newline='\n')
E=R/'evidence/eh-control-20260910';E.mkdir()
(E/'integration.json').write_text(json.dumps(dict(source=str(C/'k7ehcontrol_main.cxx'),
sha256=hashlib.sha256(data).hexdigest(),target='app/k7ehcontrol/k7ehcontrol_main.cxx',hardware_tested=False),indent=2)+'\n')
print('Prepared isolated eh-control firmware')
