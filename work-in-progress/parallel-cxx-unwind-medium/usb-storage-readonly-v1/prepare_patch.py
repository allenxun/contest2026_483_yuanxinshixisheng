"""Build an unapplied candidate against frozen SDK inputs only."""
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'evidence/usb-storage-inputs-20260910/nuttx'
patch=[]; inputs=[]
for relative in ['drivers/usbhost/Kconfig','drivers/usbhost/usbhost_storage.c']:
    p=BASE/relative; raw=p.read_bytes(); old=raw.decode('utf-8'); new=old
    if relative.endswith('Kconfig'):
        before='config USBHOST_MSC_NOTIFIER\n'
        insertion='''config USBHOST_MSC_READONLY
\tbool "Read-only USB mass storage block devices"
\tdefault n
\tdepends on USBHOST_MSC
\t---help---
\t\tReject all block write requests before submitting any USB transfer and
\t\treport the device geometry as not write-enabled. This applies to all
\t\tdevices handled by the USB mass storage class. Filesystems must support
\t\tmounting genuinely read-only block devices.

'''
        assert new.count(before)==1
        new=new.replace(before,insertion+before)
    else:
        start=new.index('static ssize_t usbhost_write(FAR struct inode *inode,',new.index(' * Name: usbhost_write'))
        pos=new.index('{',start)+1
        new=new[:pos]+'''
#ifdef CONFIG_USBHOST_MSC_READONLY
  /* Reject before touching the class state or sending a WRITE10 CBW. */

  return -EROFS;
#endif
'''+new[pos:]
        before='          geometry->geo_writeenabled  = true;'
        assert new.count(before)==1
        new=new.replace(before,'''#ifdef CONFIG_USBHOST_MSC_READONLY
          geometry->geo_writeenabled  = false;
#else
'''+before+'''
#endif''')
    assert old!=new
    patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
    inputs.append(dict(path=relative,sha256=hashlib.sha256(raw).hexdigest(),output_sha256=hashlib.sha256(new.encode('utf-8')).hexdigest()))
(HERE/'msc-readonly.patch').write_text(''.join(patch),encoding='utf-8')
(HERE/'patch-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
print('Generated default-off two-file candidate; NOT APPLIED')
