import pathlib,os,subprocess,time,datetime,json,csv,sys,psutil
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
r=pathlib.Path(__file__).resolve().parents[1];model='E:/openvela/语音模块/openvela-voicelink/models'
wav=model+'/sherpa-onnx-streaming-paraformer-bilingual-zh-en/test_wavs/0.wav'
out=r/'evidence'/('suite-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
env=os.environ.copy();env['PATH']=str(r.parent/'parallel-voicelink-runtime/runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib')+os.pathsep+env['PATH']
jobs=[]
for tail in [0,300,800,1200,2000]:jobs.append(('tail-'+str(tail),'asr',wav,512,tail,0,0,1024,'normal',0))
jobs.extend([('chunk-160','asr',wav,160,800,0,0,1024,'normal',0),
 ('whole-input','asr',wav,1000000,800,300,1,1024,'normal',0),
 ('endpoint','asr',wav,512,800,0,1,1024,'normal',0),
 ('cancel','asr',wav,512,800,0,0,1024,'cancel',20),
 ('empty','asr',wav,512,0,0,0,1024,'empty',0),
 ('budget-zero','asr',wav,512,800,0,0,0,'normal',21),
 ('synthetic-tail0','asr',str(r.parent/'parallel-voicelink-runtime/evidence/tts-binding.wav'),512,0,0,0,1024,'normal',0),
 ('synthetic-tail800','asr',str(r.parent/'parallel-voicelink-runtime/evidence/tts-binding.wav'),512,800,0,0,1024,'normal',0)])
for repeat in range(3):
    modes=['asr','tts','both','sequential'] if repeat!=1 else ['sequential','both','tts','asr']
    for mode in modes:jobs.append(('memory-'+mode+'-'+str(repeat+1),mode,wav,512,800,0,0,1024,'normal',0))
if len(sys.argv)>1 and sys.argv[1]=='extra':
    jobs=[('whole-no-lead','asr',wav,1000000,800,0,0,1024,'normal',0),
          ('lead300-chunk512','asr',wav,512,800,300,0,1024,'normal',0)]
# Reference is declared before execution: published model output, NOT human transcript.
(out/'expectations.json').write_text(json.dumps({'natural_reference_source':'https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/paraformer-models.html',
 'natural_reference_kind':'published model output, not independently verified human ground truth',
 'natural_reference_text':'昨天是 monday today day is 零八二 the day after tomorrow 是星期三',
 'synthetic_expected_text':'你好，欢迎使用语音助手。','synthetic_kind':'known generation input; not natural speech accuracy',
 'budgets':'fixed max 1024 decodes per drain; zero budget intentionally rejects ready input'},ensure_ascii=False,indent=2),encoding='utf-8')
results=[]
for label,mode,audio,chunk,tail,lead,endpoint,budget,action,expected in jobs:
    d=out/label;d.mkdir();cmd=[str(r/'probe.exe'),mode,model,audio,str(chunk),str(tail),str(lead),str(endpoint),str(budget),action]
    samples=[];begin=time.perf_counter();timeout=False
    with (d/'stdout.raw').open('wb') as so,(d/'stderr.raw').open('wb') as se:
        child=subprocess.Popen(cmd,cwd=str(r),env=env,stdout=so,stderr=se);proc=psutil.Process(child.pid)
        while child.poll() is None:
            try:
                m=proc.memory_info();samples.append([time.perf_counter()-begin,m.rss,getattr(m,'private',0),getattr(m,'peak_wset',0)])
            except psutil.Error:pass
            if time.perf_counter()-begin>60:child.kill();timeout=True
            time.sleep(.02)
        code=child.wait()
    with (d/'memory.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['seconds','working_set_bytes','private_bytes','os_peak_working_set_bytes']);writer.writerows(samples)
    text=(d/'stdout.raw').read_bytes().decode('utf-8',errors='replace')
    (d/'stdout.txt').write_text(text,encoding='utf-8');(d/'stderr.txt').write_text((d/'stderr.raw').read_bytes().decode('utf-8',errors='replace'),encoding='utf-8')
    report={'label':label,'command':cmd,'exit_code':code,'expected_exit_code':expected,'execution_passed':code==expected and not timeout,'timeout':timeout,
      'elapsed':time.perf_counter()-begin,'peak_working_set':max((s[1] for s in samples),default=0),'peak_private':max((s[2] for s in samples),default=0),
      'os_peak_working_set':max((s[3] for s in samples),default=0),'samples':len(samples),'sample_interval':.02}
    (d/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');results.append(report)
    print(label,'exit',code,[line for line in text.splitlines() if line.startswith(('text=','decodes=','failure='))],flush=True)
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('Evidence:',out)
sys.exit(0 if all(x['execution_passed'] for x in results) else 1)
