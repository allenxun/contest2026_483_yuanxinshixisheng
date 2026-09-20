"""Export explicitly scoped VelaVision primary sessions with provenance.
No rewriting original transcripts, synthetic events, uploads or Git operations.
"""
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
_deps=Path(__file__).resolve().parents[1]/'private/log-dependencies'
if _deps.is_dir():
    sys.path.insert(0,str(_deps))
    os.environ['PYTHONPATH']=str(_deps)+os.pathsep+os.environ.get('PYTHONPATH','')
from log_export_core import Cleaner, convert
from log_daily import write_session
from jsonschema import Draft7Validator, FormatChecker

ROOT=Path(__file__).resolve().parents[1]
TEAM='contest2026_483_yuanxinshixisheng'
LOGIN='maomaojiang01'
def sha(b): return hashlib.sha256(b).hexdigest()
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')

def _export_locked():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,default=ROOT/'tools/log-sources.json')
    parser.add_argument('--secrets',type=Path,default=ROOT.parent/'本地私密配置/wireless-auth.json')
    args=parser.parse_args()
    auth=json.loads(args.secrets.read_text(encoding='utf-8-sig'))
    values=auth.get('redaction_values',[])+[auth['password']]
    sources=json.loads(args.sources.read_text(encoding='utf-8'))
    schema=ROOT/'tools/official-validator/schema'
    ev=Draft7Validator(json.loads((schema/'event.schema.json').read_bytes()),format_checker=FormatChecker())
    mv=Draft7Validator(json.loads((schema/'manifest.schema.json').read_bytes()),format_checker=FormatChecker())
    sessions=[]; reports=[]
    for source in sources:
        cleaner=Cleaner(values)
        original=Path(source['path'])
        raw=original.read_bytes()
        events,report=convert(raw,cleaner,expected_sid=source['id'],expected_workspace=source['cwd'])
        for seq,event in enumerate(events):
            event.update(schema_version='1.0',session_id=source['id'],team_id=TEAM,github_login=LOGIN,tool='codex',seq=seq)
            ev.validate(event)
        blob=''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events).encode('utf-8')
        for secret in cleaner.secrets: assert secret.encode() not in blob
        parts=write_session(ROOT,LOGIN,source['id'],events,report['started_at'])
        rel=parts[-1]['file_path']
        warning=('Explicitly selected project primary sessions, including the user-provided VoiceLink handoff. The 2026-09-03 session was outside the current E: workspace and is included under the user request to consolidate previous and current VelaVision development. '
                 'Manual native Codex Desktop JSONL backfill; not automatic hook acceptance. No internal reasoning, system/developer prompts, ambient context, inline media or secrets. '
                 'No additional text truncation; source-side truncation cannot be recovered. Child-agent transcripts are not separately duplicated. Outstanding tools at snapshot cutoff remain unresolved.')
        sessions.append(dict(session_id=source['id'],tool='codex',started_at=report['started_at'],last_event_at=events[-1]['ts'],
                             event_count=len(events),file_path=rel,collection_mode='vscode_extension_partial',health='degraded',
                             data_completeness_warning=warning,source_surface='Codex Desktop',collection_method='manual-native-jsonl-snapshot',
                             sha256=sha(blob),sha256_scope='complete session stream',files=parts,redacted_count_total=sum(cleaner.counts.values())))
        report.update(source_path=str(original),export_sha256=sha(blob),file_path=rel,label=source['label'])
        reports.append(report)
    manifest_path=ROOT/f'logs/{LOGIN}/manifest.json'
    if manifest_path.exists():
        previous=json.loads(manifest_path.read_bytes())
        if previous['team_id'] != TEAM or previous['github_login'] != LOGIN:
            raise ValueError('Existing manifest identity mismatch')
        replaced={(s['tool'],s['session_id']) for s in sessions}
        sessions += [s for s in previous['sessions'] if (s['tool'],s['session_id']) not in replaced]
    manifest=dict(schema_version='1.0',team_id=TEAM,github_login=LOGIN,generator='velavision-scoped-backfill@2.1',updated_at=now(),sessions=sessions)
    mv.validate(manifest)
    dump(ROOT/f'logs/{LOGIN}/manifest.json',manifest)
    dump(ROOT/'evidence/log-snapshots.json',dict(sessions=reports,scope='explicit project primary sessions including VoiceLink handoff',remote_submission=False))
    validator=ROOT/'tools/official-validator/tools/validate-log.py'
    proc=subprocess.run([sys.executable,'-X','utf8',str(validator),str(ROOT/'logs')],capture_output=True,text=True,encoding='utf-8')
    (ROOT/'evidence/official-log-validation.txt').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    dump(ROOT/'evidence/official-log-validation.json',dict(checked_at=now(),exit_code=proc.returncode,stdout=proc.stdout,stderr=proc.stderr,
         validator_sha256=sha(validator.read_bytes()),validator_commit='10743591d1034480ecee7c8ffffe9bb251d4474d',
         source_snapshots=len(sessions),events=sum(s['event_count'] for s in sessions),
         log_hashes={s['file_path']:s['sha256'] for s in sessions},remote_submission=False))
    print(proc.stdout)
    if proc.returncode: raise SystemExit(proc.returncode)
    print(json.dumps(dict(sessions=len(sessions),events=sum(s['event_count'] for s in sessions),reports=[dict(label=r['label'],events=r['exported_events']) for r in reports]),ensure_ascii=False))

def main():
    # Keep programmatic callers under the same lock as the CLI and Stop hook.
    if os.name == 'nt':
        from auto_collect_logs import writer_lock
        with writer_lock():
            return _export_locked()
    else:
        return _export_locked()

if __name__=='__main__':
    main()
