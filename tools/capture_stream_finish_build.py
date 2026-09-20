"""Preserve initial artifact, fix error propagation, sync, then rebuild."""
import base64,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
source=(ROOT/'app/k7sound/pio.c').read_bytes()
old=source.decode().replace('        int sink_rc;\n','').replace('        sink_rc=sink(sink_arg,capture[2*out->frames],capture[2*out->frames+1]);\n        if(sink_rc){rc=sink_rc;goto done;}','        rc=sink(sink_arg,capture[2*out->frames],capture[2*out->frames+1]);\n        if(rc)goto done;')
# Local write_text used Windows newline translation during the first stage.
old=old.replace('\r\n','\n')
expected=[hashlib.sha256(old.encode()).hexdigest(),hashlib.sha256(old.replace('\n','\r\n').encode()).hexdigest()]
code='''import base64,hashlib,json,pathlib,subprocess,shutil
sdk=pathlib.Path('/home/swl/openvela');root=sdk/'work/velavision-project'
p=sdk/'apps/examples/k7sound/pio.c'
digest=hashlib.sha256(p.read_bytes()).hexdigest()
assert digest in %r, digest
ev=root/'evidence/capture-stream-20260914'
out=sdk/'cmake_out/velavision_capture_stream_20260914'
shutil.copyfile(out/'nuttx.bin',ev/'initial-before-error-fix.bin')
bp=root/'evidence/sync/capture-stream-baseline-20260914.json'
b=json.loads(bp.read_text());b['app/k7sound/pio.c']=digest;bp.write_text(json.dumps(b))
(root/'app/k7sound/pio.c').write_bytes(base64.b64decode(%r))
args=['/usr/bin/python3.10',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk),'--include','app/k7sound/pio.c']
subprocess.check_call(args+['--check']);subprocess.check_call(args+['--apply']);subprocess.check_call(args+['--check'])
with (ev/'arm64-build-final.log').open('xb') as log:
 rc=subprocess.call(['bash','-c','source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_capture_stream_20260914 -j4'],cwd=str(sdk),stdout=log,stderr=subprocess.STDOUT)
assert rc==0
symbols=subprocess.check_output([str(sdk/'prebuilts/gcc/linux-x86_64/aarch64-none-elf/bin/aarch64-none-elf-nm'),str(out/'nuttx')]).decode()
r={'build_exit_code':rc,'board_loaded':False,'symbols':{s:any(x.endswith(' '+s) for x in symbols.splitlines()) for s in ['k7sound_capture_stream','pio_run_grouped_sink','k7_stream_ring_sample','k7cloud_capture_stream_probe']},'firmware':{'bytes':(out/'nuttx.bin').stat().st_size,'sha256':hashlib.sha256((out/'nuttx.bin').read_bytes()).hexdigest()}}
assert all(r['symbols'].values())
(ev/'arm64-result.json').write_text(json.dumps(r,indent=2))
print('RESULT_JSON='+json.dumps(r))
''' % (expected,base64.b64encode(source).decode())
result=remote(code).decode()
print(result)
record=json.loads(result.split('RESULT_JSON=')[-1])
(ROOT/'evidence/capture-stream-20260914/arm64-result.json').write_text(json.dumps(record,indent=2)+'\n')
