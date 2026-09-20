from pathlib import Path
import subprocess,os
p=Path(__file__).parent.resolve();s=(p/'env-gate.cc').read_text();start=s.index('      const int ret = pthread_join(hThread, &res);');end=s.index('#elif defined(NDEBUG)',start);body=s[start:end]
code='''#include <pthread.h>
#include <exception>
#include <cstdlib>
#include <cstdio>
#include <cassert>
#include <cerrno>
static int injected;
static int joined(pthread_t t,void **p){int rc=pthread_join(t,p);return rc?rc:injected;}
#define pthread_join joined
static void *work(void *p){return p;}
static void checked(pthread_t hThread){void *res;
'''+body+'''
}
int main(int argc,char**){std::set_terminate([]{std::_Exit(77);});injected=argc>1?EINVAL:0;
pthread_t t;assert(!pthread_create(&t,nullptr,work,nullptr));checked(t);
std::puts("JOIN_PROVEN_RELEASE_ALLOWED");return 0;}
'''
(p/'test_join.cpp').write_text(code)
cc='D:/software/mingw64/mingw64/bin/g++.exe';env=dict(os.environ);env['PATH']=str(Path(cc).parent)+os.pathsep+env.get('PATH','');logs=[]
for opt in ['O0','O2']:
 exe=str(p/('join-'+opt+'.exe'));cmd=[cc,'-std=c++17','-'+opt,'-Wall','-Wextra','-Werror','-pthread','test_join.cpp','-o',exe]
 r=subprocess.run(cmd,cwd=p,env=env,capture_output=True,text=True,timeout=30);logs +=[repr(cmd),r.stdout,r.stderr];assert not r.returncode,(r.stdout,r.stderr)
 for args,ret in [([exe],0),([exe,'inject-join-error'],77)]:
  r=subprocess.run(args,cwd=p,env=env,capture_output=True,text=True,timeout=15);logs +=[repr(args),r.stdout,r.stderr,'exit='+str(r.returncode)];assert r.returncode==ret
  if ret:assert 'RELEASE_ALLOWED' not in r.stdout
# Actual caller-source structure checks, no mocked successful ORT build.
t=(p/'input/2-tensorprotoutils.cc').read_text();assert t.index('auto status = env.MapFileIntoMemory')<t.index('auto buffer = std::make_unique<char[]>(length)')<t.index('ORT_RETURN_IF_ERROR(env.ReadFileIntoBuffer',t.index('auto status = env.MapFileIntoMemory'))
m=(p/'input/1-model.cc').read_text();assert 'GetCanonicalPath' not in m;assert 'FileInputStream input(fd, block_size)' in m
logs.append('PASS source-path checks: map failure copy fallback and ordinary model no canonical call; no full ORT compile')
(p/'test-output.txt').write_text('\n'.join(logs));print('\n'.join(logs))
