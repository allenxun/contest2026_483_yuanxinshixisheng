"""Archive this turn's superseded builds; remove only after verified E: copies."""
import base64,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
names=['velavision_native_photo_20260915','velavision_device_loop_20260915']
out=ROOT/'evidence/native-intermediate-archives-20260915'
out.mkdir(exist_ok=True)
for name in names:
    payload=json.loads(remote('''import pathlib,tarfile,io,base64,hashlib,json
name=%r
root=pathlib.Path('/home/swl/openvela/cmake_out').resolve();p=(root/name).resolve()
assert p.parent==root and p.name==name and p.is_dir()
files=[n for n in ['nuttx','nuttx.bin','System.map','.config','compile_commands.json','CMakeCache.txt'] if (p/n).is_file()]
assert all(n in files for n in ['nuttx','nuttx.bin','System.map'])
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as tar:
 for n in files:tar.add(p/n,arcname=n)
blob=data.getvalue()
print(json.dumps({'archive':base64.b64encode(blob).decode(),'sha256':hashlib.sha256(blob).hexdigest(),
 'files':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in files}}))
'''%name))
    raw=base64.b64decode(payload.pop('archive'))
    assert hashlib.sha256(raw).hexdigest()==payload['sha256']
    dest=out/(name+'.tar.gz')
    if dest.exists() and dest.read_bytes()!=raw:raise RuntimeError('Refuse replace archive')
    dest.write_bytes(raw)
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==payload['sha256']
    (out/(name+'.json')).write_text(json.dumps(payload,indent=2))
    print('Archived and verified',name,len(raw),flush=True)
    print(remote('''import pathlib,hashlib,shutil,subprocess
name=%r;expected=%r
root=pathlib.Path('/home/swl/openvela/cmake_out').resolve();p=(root/name).resolve()
assert p.parent==root and p.name in ['velavision_native_photo_20260915','velavision_device_loop_20260915']
for n,digest in expected.items():assert hashlib.sha256((p/n).read_bytes()).hexdigest()==digest
revision=name.replace('velavision_','').replace('_20260915','-20260915').replace('_','-')
ev=pathlib.Path('/home/swl/openvela/work/velavision-project/evidence')/revision
assert (ev/'build.exit').read_text().strip()=='0'
processes=subprocess.check_output(['ps','-eo','args']).decode()
assert not any(str(p) in line and ('cmake --build' in line or 'ninja' in line) for line in processes.splitlines())
shutil.rmtree(p)
print('Removed verified regenerable directory',p)
'''%(name,payload['files'])).decode())
print(remote("import subprocess;print(subprocess.check_output(['df','-h','/']).decode())").decode())
