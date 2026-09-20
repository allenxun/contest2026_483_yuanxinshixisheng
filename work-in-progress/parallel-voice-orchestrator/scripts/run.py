from pathlib import Path
import subprocess,datetime,json,os,time,hashlib,wave,ctypes
import psutil
R=Path(__file__).resolve().parents[1]
run=R/'evidence'/('run-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
run.mkdir()
cc=Path(r'D:\software\mingw64\mingw64\bin')
lib=R.parent/'parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib'
models=Path(r'E:\openvela\语音模块\openvela-voicelink\models')
env=os.environ.copy();env['PATH']=str(lib)+';'+str(cc)+';'+env.get('PATH','')
records=[]
ort=ctypes.CDLL(str(lib/'onnxruntime.dll'))
ort.OrtGetApiBase.restype=ctypes.POINTER(ctypes.c_void_p)
ort_version=ctypes.CFUNCTYPE(ctypes.c_char_p)(ort.OrtGetApiBase()[1])().decode()
assert ort_version=='1.17.1',ort_version
assert hashlib.sha256((R/'vendor/sherpa-onnx/c-api/c-api.h').read_bytes()).hexdigest()=='e286ded904e93b670ad229d88151dfade58671fc2740a0afb11b0372f3595100'
(run/'versions.json').write_text(json.dumps({'ort':ort_version,'sherpa':'1.12.14','provider':'cpu','threads':1}),encoding='utf8')
def execute(name,args,expected=0,limit=60):
 out=run/(name+'.stdout.raw');err=run/(name+'.stderr.raw')
 t=time.monotonic();peak=0;samples=[];timedout=False
 with out.open('xb') as o,err.open('xb') as e:
  p=subprocess.Popen([str(x) for x in args],stdout=o,stderr=e,cwd=R,env=env)
  proc=psutil.Process(p.pid)
  while p.poll() is None:
   try:
    m=proc.memory_info();private=getattr(m,'private',m.rss);peak=max(peak,private)
    samples.append([time.monotonic()-t,private,m.rss])
   except psutil.Error:pass
   if time.monotonic()-t>limit:
    timedout=True;p.kill();p.wait();break
   time.sleep(.02)
 rec=dict(name=name,command=[str(x) for x in args],exit=p.returncode,expected=expected,
          timeout=timedout,seconds=time.monotonic()-t,peak_private_bytes=peak)
 records.append(rec)
 (run/(name+'.memory.json')).write_text(json.dumps(samples),encoding='utf8')
 (run/'results.json').write_text(json.dumps(records,indent=2),encoding='utf8')
 print(name,rec['exit'],round(rec['seconds'],3),flush=True)
 if p.returncode!=expected or timedout:raise RuntimeError(name+' failed; raw evidence retained')
flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror','-finput-charset=UTF-8','-fexec-charset=UTF-8','-I',R/'include','-I',R/'vendor']
execute('build-machine',[cc/'g++.exe',*flags,R/'tests/test_machine.cpp','-o',run/'machine.exe'])
execute('mock-machine',[run/'machine.exe'])
execute('build-broker',[cc/'gcc.exe','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',R/'include','-c',R/'src/wifi_broker.c','-o',run/'broker.o'])
execute('build-wifi',[cc/'g++.exe',*flags,R/'tests/test_wifi.cpp',run/'broker.o','-o',run/'wifi.exe'])
execute('mock-wifi',[run/'wifi.exe'])
execute('build-real',[cc/'g++.exe',*flags,R/'src/demo.cpp',R/'src/audio.cpp',run/'broker.o',lib/'sherpa-onnx-c-api.lib','-o',run/'demo.exe'])
wav=models/'sherpa-onnx-streaming-paraformer-bilingual-zh-en/test_wavs/0.wav'
for name,policy,cancel,task in [('real-release','release','0','example'),('real-hold','hold','0','example'),('real-wifi-mock','release','0','wifi-mock'),('real-cancel','release','50','example')]:
 execute(name,[run/'demo.exe',models,wav,run/(name+'.wav'),policy,cancel,task],20 if cancel!='0' else 0)
 if cancel=='0':
  with wave.open(str(run/(name+'.wav'))) as w:assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,8000) and w.getnframes()>0
  log=(run/(name+'.stdout.raw')).read_text(encoding='utf8')
  assert log.count('mark=asr_load_begin')==1 and log.count('mark=tts_load_begin')==1
  assert log.index('mark=asr_finished')<log.index('mark=release_complete')<log.index('mark=tts_load_begin')
  assert 'transcript=昨天是 monday today day is 礼拜二 the day after tomorrow 是星期三' in log
 else:assert not (run/(name+'.wav')).exists()
# Real missing model/WAV errors separate from injected core events.
execute('real-invalid-model',[run/'demo.exe',run/'absent-models',wav,run/'absent.wav','release','0','example'],3)
execute('real-invalid-wav',[run/'demo.exe',models,run/'absent.wav',run/'no.wav','release','0','example'],3)
hashes=[]
for p in [wav,*lib.glob('*.dll'),lib/'sherpa-onnx-c-api.lib',models/'sherpa-onnx-streaming-paraformer-bilingual-zh-en/encoder.int8.onnx',models/'sherpa-onnx-streaming-paraformer-bilingual-zh-en/decoder.int8.onnx',models/'vits-icefall-zh-aishell3/model.onnx']:
 hashes.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(run/'runtime-inputs.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf8')
print('EVIDENCE='+str(run),flush=True)
