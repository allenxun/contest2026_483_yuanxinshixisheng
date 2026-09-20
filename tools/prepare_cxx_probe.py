"""Create a separate C++ prerequisite build, without changing the running image."""
from pathlib import Path
import re
R = Path(__file__).resolve().parents[1]
profile = R/'board/kickpi_k7/configs/velavision_cxx_probe_local/defconfig'
if profile.exists():
    raise SystemExit('Candidate exists; do not regenerate over reviewed changes')
settings = {
    'HAVE_CXX': 'y', 'HAVE_CXXINITIALIZE': 'y', 'TLS_NELEM': '8',
    'TLS_NCLEANUP': '8', 'LIBCXX': 'y', 'LIBCXXABI': 'y',
    'LIBCXX_VERSION': '"17.0.6"', 'LIBCXXABI_VERSION': '"17.0.6"',
    'CXX_STANDARD': '"gnu++17"', 'CXX_EXCEPTION': 'y', 'CXX_RTTI': 'y',
    'EXAMPLES_K7CXX': 'y', 'PTHREAD_MUTEX_TYPES': 'y',
}
base = (R/'board/kickpi_k7/configs/velavision_smp_load_local/defconfig').read_text()
for key, value in settings.items():
    base = re.sub(r'^(?:CONFIG_'+key+r'=.*|# CONFIG_'+key+r' is not set)\n?', '', base, flags=re.M)
    base += 'CONFIG_'+key+'='+value+'\n'
profile.parent.mkdir(parents=True)
profile.write_text(base, newline='\n')
shell = (R/'tools/build_smp_load.sh').read_text().replace('smp_load', 'cxx_probe')
(R/'tools/build_cxx_probe.sh').write_text(shell, newline='\n')
script = (R/'tools/build_smp_load_vm.py').read_text()
script = script.replace('smp-load', 'cxx-probe').replace('smp_load', 'cxx_probe')
# Old hashes only cover unchanged existing formal sources. New paths must not
# overwrite an unknown mirror file; the staging script refuses that case.
script = script.replace("private/cxx-probe-original-hashes.json", "private/smp-load-original-hashes.json")
script = script.replace("paths=list(dict.fromkeys(paths))", "paths += [str(p.relative_to(R)).replace('\\\\','/') for p in sorted((R/'app/k7cxx').iterdir()) if p.is_file()]\npaths=list(dict.fromkeys(paths))")
script = script.replace("['CONFIG_EXAMPLES_K7LOAD=y',", "['CONFIG_EXAMPLES_K7CXX=y','CONFIG_HAVE_CXX=y','CONFIG_LIBCXX=y','CONFIG_LIBCXXABI=y','CONFIG_CXX_EXCEPTION=y','CONFIG_CXX_RTTI=y','CONFIG_TLS_NELEM=8','CONFIG_EXAMPLES_K7LOAD=y',")
(R/'tools/build_cxx_probe_vm.py').write_text(script, newline='\n')
print(profile)
