"""Run a real local executable, recording command, raw streams and process memory."""
import sys,os,time,json,pathlib,datetime,subprocess,psutil
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
root=pathlib.Path(__file__).resolve().parents[1]
label=sys.argv[1];cmd=sys.argv[2:]
out=root/'evidence'/(label+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir()
env=os.environ.copy();lib=root/'runtime/sherpa-onnx-v1.12.14-win-x64-shared/lib'
env['PATH']=str(lib)+os.pathsep+env.get('PATH','')
t=time.perf_counter();peak_rss=peak_private=peak_wset=0;count=0;timed_out=False
with (out/'stdout.raw').open('wb') as stdout,(out/'stderr.raw').open('wb') as stderr:
    child=subprocess.Popen(cmd,cwd=str(root),env=env,stdout=stdout,stderr=stderr)
    proc=psutil.Process(child.pid)
    while child.poll() is None:
        try:
            m=proc.memory_info();peak_rss=max(peak_rss,m.rss);peak_private=max(peak_private,getattr(m,'private',0));peak_wset=max(peak_wset,getattr(m,'peak_wset',0));count+=1
        except psutil.Error:pass
        if time.perf_counter()-t>180: child.kill();timed_out=True
        time.sleep(.02)
    code=child.wait()
report={'command':cmd,'cwd':str(root),'exit_code':code,'timed_out':timed_out,'elapsed_seconds':time.perf_counter()-t,
        'sample_interval_seconds':.02,'samples':count,'sampled_peak_rss_bytes':peak_rss,'sampled_peak_private_bytes':peak_private,'observed_os_peak_working_set_bytes':peak_wset,
        'method':'psutil Windows process memory_info polled every 20ms; single child process, not device/model-only memory; transient peaks may be missed'}
for kind in ['stdout','stderr']:
    raw=(out/(kind+'.raw')).read_bytes();(out/(kind+'.txt')).write_text(raw.decode('utf-8',errors='replace'),encoding='utf-8')
    print(raw.decode('utf-8',errors='replace')[-4500:])
(out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));print(out)
sys.exit(0 if code==0 and not timed_out else 1)
