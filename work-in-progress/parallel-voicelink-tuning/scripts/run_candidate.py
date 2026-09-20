import pathlib,subprocess,os,json,time,datetime,sys
sys.stdout.reconfigure(encoding='utf8',errors='replace')
r=pathlib.Path(__file__).resolve().parents[1]
d=r/'evidence'/('candidate-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));d.mkdir()
env=os.environ.copy();env['PATH']=str(r.parent/'parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib')+os.pathsep+env['PATH']
cmd=[str(r/'candidate_test.exe'),'E:/openvela/语音模块/openvela-voicelink/models','E:/openvela/语音模块/openvela-voicelink/models/sherpa-onnx-streaming-paraformer-bilingual-zh-en/test_wavs/0.wav']
t=time.perf_counter()
try:
    p=subprocess.run(cmd,cwd=str(r),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60);so,se,code=p.stdout,p.stderr,p.returncode
except subprocess.TimeoutExpired as e:so,se,code=e.stdout or b'',e.stderr or b'',124
(d/'stdout.raw').write_bytes(so);(d/'stderr.raw').write_bytes(se)
(d/'stdout.txt').write_text(so.decode('utf8',errors='replace'),encoding='utf8')
(d/'result.json').write_text(json.dumps({'command':cmd,'exit_code':code,'elapsed':time.perf_counter()-t},ensure_ascii=False,indent=2),encoding='utf8')
print(so.decode('utf8',errors='replace'));print(d);sys.exit(0 if code==0 else 1)
