"""Copy a pinned, unmodified upstream WPA core subset; retain license/provenance."""
import hashlib,json,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
archive=root/'third_party/downloads/wpa_supplicant-2.12.tar.gz'
expected='08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
src=root/'third_party/wpa_supplicant-2.12'
dst=root/'app/k7radio/hostap'
files='''rsn_supp/wpa.c rsn_supp/wpa_ie.c rsn_supp/pmksa_cache.c
common/wpa_common.c common/ieee802_11_common.c
utils/common.c utils/wpabuf.c utils/bitfield.c
crypto/aes-internal.c crypto/aes-internal-enc.c crypto/aes-internal-dec.c
crypto/aes-unwrap.c crypto/aes-wrap.c crypto/aes-omac1.c
crypto/sha1.c crypto/sha1-internal.c crypto/sha1-prf.c crypto/sha1-pbkdf2.c
crypto/sha256.c crypto/sha256-internal.c crypto/sha256-prf.c
crypto/md5.c crypto/md5-internal.c crypto/rc4.c'''.split()
paths=list((src/'src').rglob('*.h'))+[src/'src'/p for p in files]
hashes={}
for p in paths:
    rel=p.relative_to(src/'src'); target=dst/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(p,target)
    hashes[str(rel).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copyfile(src/'COPYING',dst/'COPYING')
(dst/'provenance.json').write_text(json.dumps(dict(url='https://w1.fi/releases/wpa_supplicant-2.12.tar.gz',archive_sha256=expected,unmodified_files=hashes),indent=2)+'\n')
(dst/'sources.cmake').write_text('set(SKW_HOSTAP_SOURCES\n'+''.join('  hostap/'+p+'\n' for p in files)+')\n')
print('Copied',len(paths),'upstream source/header files')
