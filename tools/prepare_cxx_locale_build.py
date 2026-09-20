"""Prepare a distinct wide-character/minimal-locale native runtime build."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
profile=R/'board/kickpi_k7/configs/velavision_cxx_locale_local/defconfig'
assert not profile.exists()
s=(R/'board/kickpi_k7/configs/velavision_neon_file64_local/defconfig').read_text()
assert not any(line.startswith(('CONFIG_CXX_WCHAR=', 'CONFIG_CXX_NO_LOCALIZATION=',
                                'CONFIG_CXX_MINI_LOCALIZATION=')) for line in s.splitlines())
s+='\nCONFIG_CXX_WCHAR=y\n# CONFIG_CXX_NO_LOCALIZATION is not set\nCONFIG_CXX_MINI_LOCALIZATION=y\n'
profile.parent.mkdir(parents=True)
profile.write_text(s,newline='\n')
for name in ['build_neon_file64.sh','build_neon_file64_vm.py']:
    s=(R/'tools'/name).read_text().replace('neon-file64','cxx-locale').replace('neon_file64','cxx_locale')
    s=s.replace("['CONFIG_FS_LARGEFILE=y',", "['CONFIG_CXX_WCHAR=y','CONFIG_CXX_MINI_LOCALIZATION=y','CONFIG_FS_LARGEFILE=y',")
    (R/'tools'/name.replace('neon_file64','cxx_locale')).write_text(s,newline='\n')
print('Prepared independent cxx-locale-20260910; no hardware action')
