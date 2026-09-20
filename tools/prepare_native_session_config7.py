from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'tools/configure_native_ort_session6.py').read_text().replace('native-ort-session-config6','native-ort-session-config7').replace('config-attempt6','config-attempt7')
needle="try:\n patch('nuttx-cmake'"
insert="""try:
 entries=json.loads(Path('/dev/shm/velavision-static-deps4-20260911/build/compile_commands.json').read_text())
 entry=next(row for row in entries if row['file'].endswith('/lib_strptime.c'))
 args=shlex.split(entry['command']);flags=[];i=1
 while i<len(args):
  a=args[i]
  if a in ('-o','-MF','-MT','-MQ'):i+=2;continue
  if a in ('-MD','-MMD','-c') or a==entry['file']:i+=1;continue
  flags.append(a);i+=1
 inputs={}
 for filename in ('lib_iconv.c','legacychars.h'):
  data=(Path('/home/swl/openvela/nuttx/libs/libc/locale')/filename).read_bytes()
  (O/filename).write_bytes(data);inputs[filename]=hashlib.sha256(data).hexdigest()
 (O/'iconv-inputs.json').write_text(json.dumps(inputs,indent=2))
 assert run('iconv-compile',[args[0],*flags,'-c',str(O/'lib_iconv.c'),'-o',str(O/'iconv.o')],O)
 ar=str(Path(args[0])).replace('gcc','ar')
 assert run('iconv-archive',[ar,'rcs',str(O/'libk7_iconv.a'),str(O/'iconv.o')],O)
 patch('nuttx-cmake'"""
assert needle in s;s=s.replace(needle,insert)
s=s.replace("'-DCMAKE_BUILD_TYPE=MinSizeRel',","'-DCMAKE_BUILD_TYPE=MinSizeRel','-DIconv_INCLUDE_DIR=/home/swl/openvela/nuttx/include','-DIconv_LIBRARY='+str(O/'libk7_iconv.a'),")
s=s.replace("('.log','.json')", "('.log','.json','.c','.h')")
target=R/'tools/configure_native_ort_session7.py';assert not target.exists()
compile(s,str(target),'exec');target.write_text(s)
