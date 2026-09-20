"""Verify the unified delivery, without executing hardware-facing programs."""
import ast, hashlib, json, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    index=read(ROOT/'evidence/source-files.json')
    for entry in index['files']:
        p=ROOT/entry['path']
        assert p.is_file() and sha(p)==entry['sha256'],entry['path']
    compared=read(ROOT/'evidence/accepted-source-comparison.json')
    for entry in compared:
        assert entry['identical'] and sha(ROOT/entry['path'])==entry['baseline_sha256'],entry['path']
    build=read(ROOT/'evidence/build/integrated-build.json')
    assert build['exit_code']==0 and all(build['linked_application_symbols'].values())
    for name, entry in build['files'].items():
        assert sha(ROOT/'artifacts/integrated-20260909'/name)==entry['sha256'],name
    for profile, expected in build.get('base_binary_comparison',{}).items():
        assert sha(ROOT/'baselines'/profile/'nuttx.bin')==expected,profile
    # Only parse relocated programs; never import a controller that opens a serial port.
    for p in (ROOT/'host/vision').glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    required=('manual_model','track_overlay','photo_protocol','k7_video_receiver')
    assert all((ROOT/'host/vision'/(name+'.py')).exists() for name in required)
    tree=ET.parse(ROOT/'contest2026_483_yuanxinshixisheng.xml')
    for link in tree.findall('.//linkfile'):assert (ROOT/link.attrib['src']).exists(),link.attrib
    logmanifest=read(ROOT/'logs/maomaojiang01/manifest.json')
    assert logmanifest['github_login']=='maomaojiang01' and len(logmanifest['sessions'])==2
    assert not (ROOT/'logs/your-github-login').exists()
    snapshots=read(ROOT/'evidence/log-snapshots.json')['sessions']
    event_total=0
    for session, snapshot in zip(logmanifest['sessions'],snapshots):
        target=ROOT/session['file_path'];assert sha(target)==session['sha256']==snapshot['export_sha256']
        source=Path(snapshot['source_path'])
        with source.open('rb') as f:raw=f.read(snapshot['source_snapshot_bytes'])
        assert hashlib.sha256(raw).hexdigest()==snapshot['source_snapshot_sha256']
        lines=raw.splitlines()
        for seq,line in enumerate(target.read_text(encoding='utf-8').splitlines()):
            event=json.loads(line);assert event['seq']==seq
            origin=lines[event['metadata']['source_line']-1]
            assert hashlib.sha256(origin).hexdigest()==event['metadata']['source_record_sha256']
            assert json.loads(origin)['timestamp']==event['ts']
            event_total+=1
    proc=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/official-validator/tools/validate-log.py'),str(ROOT/'logs')],capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stdout+proc.stderr
    # Known user credentials are scanned in every delivery file, not only event text.
    from log_export_core import Cleaner
    auth=read(ROOT.parent/'本地私密配置/wireless-auth.json')
    cleaner=Cleaner(auth.get('redaction_values',[])+[auth['password']])
    checked=0
    for p in ROOT.rglob('*'):
        if not p.is_file() or '.git' in p.parts or '__pycache__' in p.parts:continue
        if p.suffix in ('.gz','.zip'):continue
        blob=p.read_bytes()
        for secret in cleaner.secrets:assert secret.encode() not in blob,'Credential in '+str(p.relative_to(ROOT))
        checked+=1
    report=dict(result='PASS',indexed_source_files=len(index['files']),accepted_source_hash_checks=len(compared),
                build_symbols=build['linked_application_symbols'],firmware_sha256=build['files']['nuttx.bin']['sha256'],
                original_log_records_verified=event_total,official_log_validator_exit_code=proc.returncode,
                log_owner='maomaojiang01',credential_scanned_files=checked,legacy_sources_preserved=True,
                hardware_joint_tested=False,remote_submission=False)
    (ROOT/'evidence/project-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
