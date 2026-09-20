"""Add genuine POSIX EnvTime and configured toolchain libm to closure audit."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/audit_native_voice_link_closure.py').read_text()
s=s.replace('native-voice-link-audit','native-voice-link-audit2').replace('velavision-link-audit-20260911','velavision-link-audit2-20260911')
needle="archives=sorted(D.rglob('*.a'));objects=sorted((S/'objects').glob('*.o'))"
replace="""# Restore the upstream POSIX time implementation under the NuttX port's explicit flag.
timecmd=json.loads(Path('/dev/shm/velavision-ort-common1-20260911/17.command.json').read_text())
cut=timecmd.index('-c')
time_source=timecmd[cut+1]
time_output=S/'objects/17.o'
command=timecmd[:cut]+['-DPLATFORM_POSIX','-c',time_source,'-o',str(time_output)]
q=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
(S/'env-time-compile.log').write_bytes(q.stdout)
(S/'env-time-command.json').write_text(json.dumps(command))
assert q.returncode==0
archives=sorted(D.rglob('*.a'));objects=sorted((S/'objects').glob('*.o'))"""
assert needle in s
s=s.replace(needle,replace)
s=s.replace('sdk.append(libgcc)',"sdk.append(libgcc)\n libm=Path(subprocess.check_output([str(compiler),'-print-file-name=libm.a'],text=True).strip())\n assert libm.is_file()\n sdk.append(libm)")
target=R/'tools/audit_native_voice_link_closure2.py'
assert not target.exists()
compile(s,str(target),'exec');target.write_text(s)
