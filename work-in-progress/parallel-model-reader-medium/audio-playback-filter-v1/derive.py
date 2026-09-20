import pathlib,subprocess,ctypes,wave,hashlib,json
r=pathlib.Path(__file__).resolve().parent
cmd=[r'D:/software/mingw64/mingw64/bin/gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','playback_filter.c','-o','filter-host.dll']
p=subprocess.run(cmd,cwd=r,capture_output=True,text=True,timeout=30)
assert p.returncode==0,p.stderr
lib=ctypes.CDLL(str(r/'filter-host.dll'));fn=lib.af_filter
ptr=ctypes.POINTER(ctypes.c_uint32)
fn.argtypes=[ptr,ctypes.c_size_t,ptr,ctypes.c_size_t,ctypes.c_uint,ctypes.c_int,ptr];fn.restype=ctypes.c_int
source=r.parents[2]/'evidence/audio-gain-20260910/voice-max-first/capture-raw32.wav'
before=source.read_bytes()
with wave.open(str(source),'rb') as w:
 assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(2,4,16000)
 n=w.getnframes();raw=w.readframes(n)
buf=(ctypes.c_uint32*(2*n)).from_buffer_copy(raw);rows=[]
for mode in [1,2]:
 out=(ctypes.c_uint32*(2*n))();sat=ctypes.c_uint32(99)
 rc=fn(buf,2*n,out,2*n,n,mode,ctypes.byref(sat));assert rc==0
 dest=r/('derived-c-'+('ma4' if mode==1 else 'ma4-hp80')+'-stereo32-16000.wav')
 with wave.open(str(dest),'wb') as w:
  w.setparams((2,4,16000,n,'NONE','not compressed'));w.writeframes(bytes(out))
 rows.append(dict(mode=mode,path=dest.name,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),saturations=sat.value,frames=n))
assert bytes(buf)==raw and source.read_bytes()==before
(r/'derived-results.json').write_text(json.dumps(dict(command=cmd,stdout=p.stdout,stderr=p.stderr,source=str(source),source_sha256=hashlib.sha256(before).hexdigest(),outputs=rows,host_only=True),indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
