from pathlib import Path
import subprocess,datetime,json,hashlib,sys
R=Path(__file__).resolve().parents[1]
run=R/'evidence'/('run-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));run.mkdir()
gcc=Path(r'D:\software\mingw64\mingw64\bin\gcc.exe')
rows=[]
def execute(name,args,limit=30):
 try:
  p=subprocess.run([str(x) for x in args],cwd=R,capture_output=True,timeout=limit)
  out,err,code,timeout=p.stdout,p.stderr,p.returncode,False
 except subprocess.TimeoutExpired as ex:
  out,err,code,timeout=ex.stdout or b'',ex.stderr or b'',None,True
 (run/(name+'.stdout.raw')).write_bytes(out);(run/(name+'.stderr.raw')).write_bytes(err)
 row=dict(name=name,command=[str(x) for x in args],exit=code,timeout=timeout,limit_seconds=limit)
 rows.append(row);(run/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
 print(name,code,timeout,out.decode('utf8',errors='replace'),err.decode('utf8',errors='replace'),flush=True)
 if code!=0 or timeout:raise RuntimeError('failed; evidence preserved')
execute('compiler-version',[gcc,'--version'])
for opt in ['O0','O2']:
 execute('build-'+opt,[gcc,'-std=c11','-'+opt,'-g','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-pedantic','-I',R/'include',R/'src/codec_txn.c',R/'tests/test_codec.c','-o',run/('test-'+opt+'.exe')])
 execute('test-'+opt,[run/('test-'+opt+'.exe')])
execute('freestanding-object',[gcc,'-std=c11','-O2','-ffreestanding','-Wall','-Wextra','-Werror','-I',R/'include','-c',R/'src/codec_txn.c','-o',run/'codec_txn.o'])
execute('undefined-symbols',[gcc.parent/'nm.exe','-u',run/'codec_txn.o'])
symbols=(run/'undefined-symbols.stdout.raw').read_text(encoding='utf8')
assert not any(x in symbols for x in ['malloc','calloc','realloc','free'])
(run/'source-hashes.json').write_text(json.dumps({str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['include','src','tests','scripts'] for p in (R/d).glob('*') if p.is_file()},indent=2),encoding='utf8')
print('EVIDENCE='+str(run))
