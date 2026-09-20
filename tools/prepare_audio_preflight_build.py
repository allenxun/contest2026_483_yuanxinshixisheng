"""Create an independent read-only audio profile; no SDK/device operations."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'work-in-progress/parallel-cxx-unwind-medium/audio-clock-preflight-v1'
    manifest = base / 'delivery.json'
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == 'b471bfa252c5cb58d8ebba46abff22a2f3844d8d02e53b8dde9af7a7d8e5e7e1'
    for row in json.loads(manifest.read_text())['files']:
        path = Path(row['path'])
        if not path.is_absolute():
            path = base / path
        assert path.resolve().is_relative_to(base)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
    profile = ROOT / 'board/kickpi_k7/configs/velavision_audio_preflight_local/defconfig'
    profile.parent.mkdir(parents=True, exist_ok=True)
    content = (ROOT / 'board/kickpi_k7/configs/velavision_usb_readonly_local/defconfig').read_text()
    content += '\nCONFIG_EXAMPLES_K7AUDIO=y\n'
    if profile.exists():
        assert profile.read_text() == content
    else:
        profile.write_text(content, newline='\n')
    for name in ['build_usb_readonly.sh', 'build_usb_readonly_vm.py']:
        text = (ROOT / 'tools' / name).read_text()
        text = text.replace('usb-readonly', 'audio-preflight').replace('usb_readonly', 'audio_preflight')
        if name.endswith('.sh'):
            text = text.replace('cmake_out/velavision_audio_preflight_20260910', '/dev/shm/velavision_audio_preflight_20260910')
            text = text.replace('cd "$sdk_dir"', 'cd "$sdk_dir"\nmkdir -p /dev/shm/velavision_audio_preflight_tmp\nexport TMPDIR=/dev/shm/velavision_audio_preflight_tmp')
            text = text.replace('-j6', '-j4')
        else:
            text = text.replace('private/audio-preflight-original-hashes.json', 'private/usb-readonly-original-hashes.json')
            needle = "paths=list(dict.fromkeys(p.replace('\\\\','/') for p in paths))"
            assert needle in text
            text = text.replace(needle, "paths += [p.relative_to(R).as_posix() for p in sorted((R/'app/k7audio').iterdir()) if p.is_file()]\n" + needle)
            text = text.replace("B=SDK/'cmake_out/velavision_audio_preflight_20260910'", "B=Path('/dev/shm/velavision_audio_preflight_20260910')")
            text = text.replace("['CONFIG_USBHOST_MSC=y',", "['CONFIG_EXAMPLES_K7AUDIO=y','CONFIG_USBHOST_MSC=y',")
            text = text.replace("p=P/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((S/rel).read_bytes())",
                                "p=P/rel;p.parent.mkdir(parents=True,exist_ok=True)\n if not p.exists() or sha(p)!=m[rel]['new']:p.write_bytes((S/rel).read_bytes())")
            # Keep the exact previously approved MSC hash audit, not a new scope.
            text = text.replace('evidence/sync/audio-preflight-attempt1.json', 'evidence/sync/usb-readonly-attempt1.json')
        dest = ROOT / 'tools' / name.replace('usb_readonly', 'audio_preflight')
        if dest.exists():
            assert dest.read_text() == text
        else:
            dest.write_text(text, newline='\n')
    print('Independent audio preflight profile ready; CRU/IOC reads only; board untouched')


if __name__ == '__main__':
    main()
