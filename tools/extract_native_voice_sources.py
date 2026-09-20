"""Extract verified pinned source archives, rejecting links and escaping paths."""
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from fetch_native_voice_sources import OUT, SOURCES

for name, repo, commit in SOURCES:
    archive = OUT / (name + '-' + commit + '.tar.gz')
    report = json.loads(archive.with_suffix('.json').read_text())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == report['sha256']
    destination = OUT / (name + '-' + commit)
    if destination.exists():
        previous = json.loads((OUT / (name + '-extracted.json')).read_text())
        assert previous['archive_sha256'] == report['sha256']
        for item in previous['files']:
            assert hashlib.sha256((destination / item['path']).read_bytes()).hexdigest() == item['sha256']
        print(name, 'existing extracted files verified', flush=True)
        continue
    prefix = name + '-' + commit
    inventory = []
    omitted = []
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        assert len(members) < 100000
        assert sum(m.size for m in members) < 2 * 1024**3
        for item in members:
            path = PurePosixPath(item.name)
            assert not path.is_absolute() and '..' not in path.parts and path.parts[0] == prefix
            assert all(':' not in part and '\\' not in part for part in path.parts)
            assert item.isdir() or item.isfile() or item.issym(), 'Unsupported archive member: ' + item.name
        destination.mkdir()
        for item in members:
            if item.issym():
                omitted.append(dict(path=item.name, target=item.linkname, reason='symlink omitted; never materialized'))
                continue
            relative = PurePosixPath(item.name).relative_to(prefix)
            target = destination.joinpath(*relative.parts)
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(item) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                inventory.append(dict(path=relative.as_posix(), bytes=item.size,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (OUT / (name + '-extracted.json')).write_text(json.dumps(dict(commit=commit,
        archive_sha256=report['sha256'], files=inventory, omitted_links=omitted, compiled=False), indent=2))
    print(name, len(inventory), 'source files extracted and hashed', flush=True)
