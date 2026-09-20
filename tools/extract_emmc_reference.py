"""Extract selected inert SDK blobs; verify Git blob identity before writing."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT.parent / '无线适配_2026-09-08' / 'official-linux-20260320'
OUT = ROOT / 'evidence' / 'emmc-source-review-20260910'
PATHS = {
    'u-boot/drivers/mmc/mmc.c',
    'u-boot/drivers/clk/rockchip/clk_rk3576.c',
    'u-boot/arch/arm/include/asm/arch-rockchip/cru_rk3576.h',
    'u-boot/include/mmc.h',
    'u-boot/include/sdhci.h',
    'kernel-6.1/drivers/mmc/host/sdhci-of-dwcmshc.c',
    'u-boot/disk/part_efi.c',
    'u-boot/drivers/mmc/rockchip_sdhci.c',
    'u-boot/drivers/mmc/sdhci.c',
}

def main():
    entries = {x['path']: x for x in json.loads((SDK / 'tree.json').read_text(encoding='utf-8'))}
    records = []
    for name in sorted(PATHS):
        entry = entries[name]
        assert entry['type'] == 'blob'
        body = subprocess.run(
            ['git', '--no-replace-objects', '--git-dir=' + str(SDK / 'object-store'),
             'cat-file', 'blob', entry['oid']], check=True, stdout=subprocess.PIPE,
            env=dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='NUL')).stdout
        assert hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() == entry['oid']
        dest = OUT / 'reference' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_bytes() != body:
            raise RuntimeError('Existing reference differs: ' + name)
        dest.write_bytes(body)
        records.append(dict(path=name, git_blob=entry['oid'], bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
    (OUT / 'manifest.json').write_text(json.dumps(dict(source=str(SDK), files=records,
        hardware_accessed=False), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Verified reference blobs:', len(records))

if __name__ == '__main__':
    main()
