import datetime, hashlib, json, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = pathlib.Path(r'D:\software\mingw64\mingw64\bin\g++.exe')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=ROOT/'evidence'/stamp
    out.mkdir(parents=True)
    report={'scope':'host fake backend only; no hardware or model calls','commands':[],'passed':False}
    def run(args, limit):
        n=len(report['commands']);start=time.monotonic()
        try:
            r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,timeout=limit)
            code=r.returncode;stdout=r.stdout;stderr=r.stderr;timeout=False
        except subprocess.TimeoutExpired as e:
            code=None;stdout=e.stdout or b'';stderr=e.stderr or b'';timeout=True
        (out/f'{n}.stdout').write_bytes(stdout);(out/f'{n}.stderr').write_bytes(stderr)
        report['commands'].append({'argv':list(map(str,args)),'timeout_seconds':limit,'timed_out':timeout,
          'exit_code':code,'elapsed_seconds':time.monotonic()-start,'stdout':f'{n}.stdout','stderr':f'{n}.stderr'})
        (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return code==0
    if not run([COMPILER,'--version'],10): return 1
    for opt in ['-O0','-O2']:
        exe=out/('tests'+opt+'.exe')
        if not run([COMPILER,'-std=c++17','-Wall','-Wextra','-Werror','-pedantic',opt,
          '-I',ROOT/'include',ROOT/'tests/test_dispatcher.cpp','-o',exe],60):return 1
        if not run([exe],10):return 1
    report['passed']=True
    report['source_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'include/dispatcher.hpp',ROOT/'tests/test_dispatcher.cpp',pathlib.Path(__file__)]}
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(out);return 0
if __name__=='__main__': sys.exit(main())
