from pathlib import Path
import datetime,hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
out=R/'evidence'/datetime.datetime.now(datetime.timezone.utc).strftime('run-%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
cmake=R/'tools/python/cmake/data/bin/cmake.exe'
tc=Path(r'D:\software\mingw64\mingw64\bin')
env=dict(os.environ,PATH=str(tc)+os.pathsep+os.environ.get('PATH',''),GIT_CEILING_DIRECTORIES=str(R/'vendor'))
rows=[]
def run(name,cmd,limit):
    start=time.monotonic();log=out/(name+'.log')
    with log.open('wb') as f:
        p=subprocess.Popen([str(x) for x in cmd],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT)
        try:rc=p.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,timeout=15)
            rc=p.wait(timeout=15)
            f.write(b'\nTIMEOUT\n')
    rows.append(dict(name=name,command=[str(x) for x in cmd],returncode=rc,limit_seconds=limit,seconds=time.monotonic()-start,log=log.name))
    (out/'commands.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    if rc:raise RuntimeError(name+' failed; see '+str(log))
try:
    run('configure',[cmake,'-S',R,'-B',out/'build','-G','MinGW Makefiles',
        '-DCMAKE_C_COMPILER='+str(tc/'gcc.exe'),'-DCMAKE_CXX_COMPILER='+str(tc/'g++.exe'),
        '-DCMAKE_MAKE_PROGRAM='+str(tc/'mingw32-make.exe'),'-DCMAKE_BUILD_TYPE=Release'],90)
    run('compile',[cmake,'--build',out/'build','--target','b0-probe','--parallel','4'],300)
    invalid=out/'invalid.gguf';invalid.write_bytes(b'not-a-GGUF\n')
    run('probe',[out/'build/b0-probe.exe',out/'missing.gguf',invalid],30)
finally:
    (out/'inputs.json').write_text(json.dumps([dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in [R/'CMakeLists.txt',R/'probe/b0.c',R/'scripts/build.py',R/'VERSION.json']],indent=2),encoding='utf8')
print(out)
