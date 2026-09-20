"""Full E: archives verified against VM manifests before removing old builds."""
import argparse,hashlib,json,subprocess,tarfile
from datetime import datetime,timezone
from pathlib import Path
from cloud_radio_stage_audit import ROOT,remote,SSH

NAMES=['board_speech_affinity_20260914','board_speech_bridge_20260914',
 'board_speech_buffered_20260914','capture_stream_20260914','cloud_radio_20260914',
 'cloud_speech_20260914','cloud_speech_20260914_v2','device_intent_20260915',
 'prompt_asr2_20260914','prompt_asr_20260914','prompt_asr_direct_cache2_20260914',
 'prompt_asr_direct_cache_20260914','prompt_asr_direct_clean_20260914',
 'prompt_asr_direct_clean_tls_20260914','prompt_asr_direct_ssid_20260914',
 'spoken_tts_gated_sharedcache2_20260914','voice_mode_20260915','voice_stage_20260915']
NAMES=['velavision_'+n for n in NAMES]
parser=argparse.ArgumentParser()
parser.add_argument('--start-at',choices=NAMES)
args=parser.parse_args()
if args.start_at:NAMES=NAMES[NAMES.index(args.start_at):]
OUT=ROOT/'evidence'/('vm-build-archive-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
OUT.mkdir(parents=True,exist_ok=False)

MANIFEST=r'''
import pathlib,hashlib,json,subprocess,os
root=pathlib.Path('/home/swl/openvela/cmake_out').resolve()
p=root/NAME
assert not p.is_symlink() and p.resolve().parent==root and p.name in ALLOWED
assert p.is_dir()
assert not any(s.split()[0] in ('ninja','cmake','cc1','cc1plus') for s in subprocess.check_output(['ps','-eo','comm,args'],text=True).splitlines())
def digest(f):
 h=hashlib.sha256()
 with f.open('rb') as s:
  while True:
   b=s.read(1024*1024)
   if not b:break
   h.update(b)
 return h.hexdigest()
entries={}
for f in sorted(p.rglob('*')):
 key=f.relative_to(p).as_posix()
 if f.is_symlink():entries[key]={'link':os.readlink(f)}
 elif f.is_file():entries[key]={'size':f.stat().st_size,'sha256':digest(f)}
 elif not f.is_dir():raise RuntimeError('Unsupported file type')
# An interrupted old build may lack final ELF/BIN. Preserve its entire tree
# too; a verified archive does not imply that its compilation succeeded.
assert all(n in entries for n in ('CMakeCache.txt','build.ninja'))
'''

def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as s:
        for b in iter(lambda:s.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

for name in NAMES:
    code=MANIFEST.replace('NAME',repr(name)).replace('ALLOWED',repr(NAMES))
    expected=json.loads(remote(code+'\nprint(json.dumps(entries))'))
    print('Archiving',name,'files',len(expected),flush=True)
    part=OUT/(name+'.tar.gz.partial')
    pack='''import pathlib,sys,gzip,tarfile
p=pathlib.Path('/home/swl/openvela/cmake_out')/%r
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1,mtime=0) as gz:
 with tarfile.open(fileobj=gz,mode='w|') as t:t.add(p,arcname=p.name)
'''%name
    with part.open('xb') as f:
        subprocess.run(SSH+['python3 -'],input=pack.encode(),stdout=f,check=True,timeout=600)
    actual={}
    with tarfile.open(part,'r:gz') as tar:
        for member in tar:
            rel=member.name.removeprefix(name+'/')
            if member.isdir():continue
            if not member.name.startswith(name+'/'):raise RuntimeError('Archive prefix mismatch')
            if member.issym():actual[rel]={'link':member.linkname};continue
            if not(member.isfile() or member.islnk()):raise RuntimeError('Unsupported archive member')
            h=hashlib.sha256();size=0
            with tar.extractfile(member) as f:
                for b in iter(lambda:f.read(1024*1024),b''):h.update(b);size+=len(b)
            actual[rel]={'size':size,'sha256':h.hexdigest()}
    assert actual==expected,'Archive content mismatch'
    archive=part.with_suffix('');part.rename(archive)
    report={'source':'/home/swl/openvela/cmake_out/'+name,'archive':str(archive),
            'archive_sha256':digest_file(archive),'files':expected,'verified':True,'source_removed':False}
    report['final_artifacts_present']=all(n in expected for n in ('nuttx','nuttx.bin','System.map'))
    report_path=OUT/(name+'.json')
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert digest_file(archive)==report['archive_sha256']
    remove=code+'\nassert entries=='+repr(expected)+'''\nimport shutil
shutil.rmtree(p)
print('verified source removed')
'''
    remote(remove)
    report['source_removed']=True
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Verified and removed',name,'archive_MiB',round(archive.stat().st_size/2**20,1),flush=True)
print(remote("import shutil,json;d=shutil.disk_usage('/home/swl/openvela');print(json.dumps({'free_GiB':d.free/2**30}))").decode())
print('archive_directory',OUT,flush=True)
