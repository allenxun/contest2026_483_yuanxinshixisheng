#!/usr/bin/env python3
"""Bounded link fix: exactly three existing experimental/BSP files."""
from pathlib import Path
import datetime, difflib, hashlib, json, tarfile

root=Path('/home/swl/openvela').resolve()
relative=[
 'nuttx/drivers/usbhost/usbhost_xhci_rk3576.c',
 'nuttx/boards/arm64/rk3576/kickpi_k7/src/kickpi_k7_boardinit.c',
 'nuttx/boards/arm64/rk3576/kickpi_k7/configs/usbenum/defconfig']
targets=[root/r for r in relative]
for p in targets:
    assert p.is_file() and p.resolve()==p and p.is_relative_to(root/'nuttx'), p
original={p:p.read_text() for p in targets}
updated=dict(original)
core,board,config=targets
assert 'k7_xhci_va_to_pa' not in updated[core]
assert 'up_addrenv_va_to_pa' in updated[core]
anchor='#include "usbhost_xhci_rk3576_trace.h"'
assert updated[core].count(anchor)==1
updated[core]=updated[core].replace('up_addrenv_va_to_pa','k7_xhci_va_to_pa').replace('up_addrenv_pa_to_va','k7_xhci_pa_to_va')
updated[core]=updated[core].replace(anchor,anchor+'''

/* Only the flat K7 BSP is supported. Its configured DRAM is identity mapped. */
#ifndef CONFIG_BUILD_FLAT
#  error K7 xHCI requires the flat identity-mapped BSP
#endif
static uintptr_t k7_xhci_va_to_pa(const void *p) { return (uintptr_t)p; }
static void *k7_xhci_pa_to_va(uintptr_t p) { return (void *)p; }
''')
assert 'int board_reset(int status)' not in updated[board]
updated[board]+='''
#ifdef CONFIG_BOARDCTL_RESET
#include <nuttx/arch.h>
#include <errno.h>
int board_reset(int status)
{
  up_systemreset();
  return -EIO;
}
#endif
'''
assert 'CONFIG_DEBUG_USB=y' not in updated[config]
updated[config]+='\nCONFIG_DEBUG_USB=y\n'
work=root/'work/rk3576-usbhost'
backup=work/('pre-linkfix-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
with tarfile.open(backup,'w:gz') as tf:
    for p in targets:tf.add(p,arcname=str(p.relative_to(root)))
diff=''.join(''.join(difflib.unified_diff(original[p].splitlines(True),updated[p].splitlines(True),
                fromfile='a/'+str(p.relative_to(root)),tofile='b/'+str(p.relative_to(root)))) for p in targets)
(work/'link-fix.patch').write_text(diff)
try:
    for p in targets:
        assert p.read_text()==original[p], 'File changed during preflight'
        p.write_text(updated[p])
except BaseException:
    for p in targets:p.write_text(original[p])
    raise
print(json.dumps({'backup':str(backup),'modified':[{str(p):hashlib.sha256(p.read_bytes()).hexdigest()} for p in targets]},indent=2))
