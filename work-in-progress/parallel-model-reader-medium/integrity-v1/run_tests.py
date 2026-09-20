import hashlib,json,os,pathlib,subprocess,tempfile,time
R=pathlib.Path(__file__).resolve().parent
E=R/'evidence';E.mkdir(exist_ok=True)
CC=pathlib.Path(r'D:\software\mingw64\mingw64\bin\gcc.exe')
env=dict(os.environ);env['PATH']=str(CC.parent)+os.pathsep+env['PATH']
records=[]
def run(args,timeout=15):
 p=subprocess.run([str(x) for x in args],cwd=R,env=env,capture_output=True,text=True,timeout=timeout)
 row=dict(command=[str(x) for x in args],timeout_seconds=timeout,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr);records.append(row)
 if p.returncode:raise RuntimeError(p.stdout+p.stderr)
try:
 run([CC,'--version'])
 flags=['-std=c11','-Wall','-Wextra','-Werror','-O2','-fstack-usage','-Ivendor']
 for source in ['sha256_vendor.c','model_integrity.c','input/formal/model_reader.c']:
  run([CC,*flags,'-c',source,'-o',E/(pathlib.Path(source).stem+'.o')],30)
 run([CC,*flags,'test_integrity.c','sha256_vendor.c','-o',E/'test_integrity.exe'],30)
 run([CC,*flags,'production_probe.c',E/'model_reader.o',E/'model_integrity.o',E/'sha256_vendor.o','-o',E/'production_probe.exe'],30)
 run([CC.parent/'nm.exe','-g','--defined-only',E/'sha256_vendor.o'])
 vectors=[b'abc',b'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq',b'a'*1000000]
 for n in [1,55,56,63,64,65,4095,4096,4097,8192,8193]:vectors.append(bytes(i%251 for i in range(n)))
 with tempfile.TemporaryDirectory(prefix='fixtures-',dir=R) as tmp:
  fixture=pathlib.Path(tmp)/'fixture.bin'
  fixture.write_bytes(b'abc')
  run([E/'production_probe.exe',fixture,'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'])
  for data in vectors:
   fixture.write_bytes(data)
   for capacity in ([1,63,64,65,4096] if len(data)==65 else [4096]):
    run([E/'test_integrity.exe',fixture,len(data),hashlib.sha256(data).hexdigest(),capacity,0,min(3,len(data)),'unused'])
  for scenario in range(1,18):
   data=b'' if scenario==14 else bytes(i%251 for i in range(9000))
   fixture.write_bytes(data)
   run([E/'test_integrity.exe',fixture,len(data),hashlib.sha256(data).hexdigest(),4096,scenario,3,'unused'])
 records.append({'fixture_cleanup':'temporary ordinary files removed','model_weights_accessed':False})
finally:
 (E/'host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':'Windows x86_64 MinGW; not NuttX','results':records},indent=2),encoding='utf-8')
print('PASS',len(records)-1,'commands; evidence/host-tests.json')



