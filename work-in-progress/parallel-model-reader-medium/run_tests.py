"""Local fixtures only; every child has a timeout; no model download."""
import ctypes, hashlib, json, os, pathlib, subprocess, tempfile, time
ROOT=pathlib.Path(__file__).resolve().parent
CC=pathlib.Path(r'D:\software\mingw64\mingw64\bin\gcc.exe')
E=ROOT/'evidence'; E.mkdir(exist_ok=True)
env=dict(os.environ); env['PATH']=str(CC.parent)+os.pathsep+env['PATH']
results=[]
def run(args, seconds):
    p=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,capture_output=True,text=True,timeout=seconds)
    results.append(dict(command=[str(x) for x in args],exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
    if p.returncode: raise RuntimeError(p.stdout+p.stderr)
try:
    run([CC,'--version'],10)
    run([CC,'-std=c11','-Wall','-Wextra','-Werror','-O2','-c','model_reader.c','-o',E/'model_reader.o'],30)
    run([CC,'-std=c11','-Wall','-Wextra','-Werror','-O2','test_reader.c','-o',E/'test_reader.exe'],30)
    with tempfile.TemporaryDirectory(prefix='fixtures-',dir=ROOT) as temp:
        temp=pathlib.Path(temp); small=temp/'small.bin'; small.write_bytes(b'0123456789abcdef')
        sparse=temp/'sparse.bin'; status={'status':'skip','reason':'not attempted'}
        args=[E/'test_reader.exe',small]
        # Mark sparse BEFORE extending; do not allocate a huge ordinary file.
        if os.name=='nt':
            import msvcrt
            k=ctypes.WinDLL('kernel32',use_last_error=True)
            k.DeviceIoControl.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.c_void_p]
            k.GetCompressedFileSizeW.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
            k.GetCompressedFileSizeW.restype=ctypes.c_uint32
            with sparse.open('w+b') as f:
                returned=ctypes.c_uint32()
                ok=k.DeviceIoControl(msvcrt.get_osfhandle(f.fileno()),0x900c4,None,0,None,0,ctypes.byref(returned),None)
                if ok:
                    f.seek(2147483648+123); f.write(b'EDGE'); f.flush()
                    high=ctypes.c_uint32(); low=k.GetCompressedFileSizeW(str(sparse),ctypes.byref(high))
                    allocated=(high.value<<32)|low
                    if allocated>1024*1024: raise RuntimeError('sparse allocated-size budget exceeded')
                    status={'status':'pass','logical_bytes':sparse.stat().st_size,'allocated_bytes':allocated,'physical_budget':1048576,'method':'FSCTL_SET_SPARSE ordinary fixture handle; GetCompressedFileSizeW'}
                    args.append(sparse)
                else: status={'status':'skip','reason':'FSCTL_SET_SPARSE unavailable','winerror':ctypes.get_last_error()}
        run(args,15)
        results.append({'sparse_fixture':status})
finally:
    (E/'host-tests.json').write_text(json.dumps({'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'hardware_tested':False,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
