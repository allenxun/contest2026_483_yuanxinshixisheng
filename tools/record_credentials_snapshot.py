"""Verify and record this development increment; preserve integration history."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    evidence=ROOT/'evidence/build/credentials-20260909'
    result=read(evidence/'verification.json')
    assert result['build_exit_code']==0 and result['test']['exit_code']==0 and result['credentials_test']['exit_code']==0
    for name,item in result['artifacts'].items():
        assert sha(ROOT/'artifacts/credentials-20260909'/name)==item['sha256'],name
    for name,digest in result['sources'].items():assert sha(ROOT/name)==digest,name
    changed=[];retained=[]
    for item in read(ROOT/'evidence/accepted-source-comparison.json'):
        name=item['path'];current=sha(ROOT/name)
        if current==item['baseline_sha256']:retained.append(name)
        else:
            assert name in {'app/k7radio/'+n for n in ('k7radio_main.c','wifi_assoc_probe.inc','CMakeLists.txt','Makefile','prov_protocol.c','prov_protocol.h','prov_service.inc')},name
            assert current==result['sources'][name]
            changed.append(dict(path=name,baseline_sha256=item['baseline_sha256'],sha256=current))
    files=[]
    for folder in ('app','board','port','patches','host','mcu','frontend','legacy','work-in-progress','skills','tools','tests'):
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    # Never print credentials. Only scan deliverable sources, docs and logs.
    from log_export_core import Cleaner
    auth=read(ROOT.parent/'本地私密配置/wireless-auth.json')
    cleaner=Cleaner(auth.get('redaction_values',[])+[auth['password']])
    scan=[ROOT/f['path'] for f in files]
    scan += [p for d in ('docs','logs') for p in (ROOT/d).rglob('*') if p.is_file()]
    for p in scan:
        blob=p.read_bytes()
        assert not any(s.encode() in blob for s in cleaner.secrets),'Credential in '+str(p.relative_to(ROOT))
    manifest=read(ROOT/'logs/maomaojiang01/manifest.json')
    for s in manifest['sessions']:assert sha(ROOT/s['file_path'])==s['sha256']
    report=dict(revision='credentials-20260909',recorded_at=datetime.now(timezone.utc).isoformat(),
        result='PASS',retained_baseline_files=retained,intentional_baseline_changes=changed,
        files=files,build_evidence='evidence/build/credentials-20260909/verification.json',
        log_manifest_sha256=sha(ROOT/'logs/maomaojiang01/manifest.json'),
        log_sessions=len(manifest['sessions']),credential_scanned_files=len(scan),hardware_tested=False)
    write(evidence/'development-snapshot.json',report)
    project=read(ROOT/'project-manifest.json')
    project['latest_development']=dict(revision=report['revision'],
        snapshot='evidence/build/credentials-20260909/development-snapshot.json',
        note='Top-level source_set and integrated_build remain the initial integration snapshot.',hardware_tested=False)
    write(ROOT/'project-manifest.json',project)
    print(json.dumps(dict(result='PASS',retained=len(retained),intentional_changes=len(changed),
        source_files=len(files),log_sessions=len(manifest['sessions']),credential_scanned_files=len(scan))))
if __name__=='__main__':main()
