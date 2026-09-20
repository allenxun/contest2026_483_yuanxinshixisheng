import difflib
import hashlib
import json
from pathlib import Path
import subprocess
H=Path(__file__).resolve().parent
R=H.parents[2]
src=H.parent/'native-sherpa-offline-stage-v1/sources/kissfft/kiss_fft_log.h'
log=R/'evidence/native-sherpa-asr-build1-20260911/build.log'
original=src.read_bytes()
(H/'original').mkdir(exist_ok=True)
(H/'candidate').mkdir(exist_ok=True)
(H/'original/kiss_fft_log.h').write_bytes(original)
text=original.decode().replace('\r\n','\n')
new=text.replace('STRINGIFY','KISS_FFT_LOG_STRINGIFY').replace('TOSTRING','KISS_FFT_LOG_TOSTRING')
(H/'candidate/kiss_fft_log.h').write_text(new, newline='\n')
(H/'candidate.patch').write_text(''.join(difflib.unified_diff(text.splitlines(True),new.splitlines(True),fromfile='a/kiss_fft_log.h',tofile='b/kiss_fft_log.h')), newline='\n')
(H/'inputs.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (src,log)},indent=2))
# Exact conflicting public definition is taken from the target compiler diagnostic.
# STRINGIFY_ helper is a test fixture, not a claimed full frozen NuttX header.
fixture='#define STRINGIFY_(x) #x\n#define STRINGIFY(x) STRINGIFY_(x)\n#define TOSTRING(x) "external-tostring"\n'
gcc='D:/software/mingw64/mingw64/bin/gcc.exe'
results=[]
def run(name, header, conflict=False, release=False):
    body=(fixture if conflict else '')+('#define NDEBUG\n' if release else '')
    body+='#include "'+header+'/kiss_fft_log.h"\n#line 123 "probe.c"\nKISS_FFT_ERROR("value=%d", 7);\n'
    f=H/(name+'.c');f.write_text(body)
    cmd=[gcc,'-E','-P','-Werror',str(f)]
    q=subprocess.run(cmd,capture_output=True,timeout=15)
    (H/(name+'.stdout')).write_bytes(q.stdout)
    (H/(name+'.stderr')).write_bytes(q.stderr)
    results.append(dict(name=name,command=cmd,returncode=q.returncode))
    return q
for release in (False,True):
    suffix='release' if release else 'debug'
    old=run('original-'+suffix,'original',release=release)
    fixed=run('candidate-'+suffix,'candidate',True,release)
    assert old.returncode==fixed.returncode==0
    assert old.stdout==fixed.stdout, (old.stdout,fixed.stdout)
    bad=run('conflicting-original-'+suffix,'original',True,release)
    assert bad.returncode!=0 and b'STRINGIFY' in bad.stderr
(H/'test-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
