"""Build an allowlisted, secret-free server bundle from the unified sources."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'deliveries' / ('speech-server-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    service = ROOT.parent / '语音模块' / 'speech-service'
    files = {f'service/{name}': service / name for name in
             ('main.py', 'aliyun_speech.py', 'audio.py')}
    for name in ('__init__.py', 'session.py', 'serve.py', 'gateway.py', 'board_bridge.py', 'live_client.py'):
        files['host/streaming_asr/' + name] = ROOT / 'host/streaming_asr' / name
    files['requirements.txt'] = ROOT / 'host/streaming_asr/requirements.txt'
    for name in ('Dockerfile', '.dockerignore', 'compose.yaml', 'README.md'):
        files[name] = ROOT / 'deploy/speech' / name
    manifest = {}
    for rel, src in files.items():
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        manifest[rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps({'created_utc': stamp,
        'deployed': False, 'files': manifest}, indent=2), encoding='utf-8')
    archive = out.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(out).as_posix(), recursive=False)
    print(json.dumps({'directory': str(out), 'archive': str(archive),
                     'file_count': len(manifest), 'deployed': False}))


if __name__ == '__main__':
    main()
