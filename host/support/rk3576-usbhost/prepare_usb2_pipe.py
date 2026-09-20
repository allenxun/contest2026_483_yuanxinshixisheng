"""Bounded K7 USB2-only experiment after external-abort diagnosis."""
from pathlib import Path
import datetime, tarfile, difflib
root = Path('/home/swl/openvela')
relative = ['nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c',
            'nuttx/arch/arm64/src/rk3576/rk3576_boot.c',
            'nuttx/boards/arm64/rk3576/kickpi_k7/configs/usbenum/defconfig',
            'nuttx/drivers/usbhost/usbhost_xhci_rk3576.c']
paths = [root/r for r in relative]
old = {p:p.read_text() for p in paths}
new = dict(old)
board, mmu, config, core = paths
anchor = '   * USB3 remains held in PHY soft reset in this first USB2-only build.'
assert anchor in new[board]
new[board] = new[board].replace(anchor, '''   * USB3 is not initialized. Select Rockchip's USB2-only PIPE status
   * override, then release both controller PHY-interface reset bits.
   * Source: rk3576_phy_cfgs[1].pipe_phystatus and property_enable(true)
   * in Rockchip develop-6.1 phy-rockchip-inno-usb2.c (0x0038, 0x0189).
   * Holding PHYSOFTRST indefinitely is not a USB3 disable mechanism.''')
anchor = '  modify(HOST + 0xc2c0, 0, 1u << 31);'
assert new[board].count(anchor) == 1
new[board] = new[board].replace(anchor, anchor + '''
  maskwrite(0x26020038, 0xffff, 0x0189); /* USB2-only PIPE override */''')
anchor = '  modify(HOST + 0xc200, 1u << 31, 0);'
assert new[board].count(anchor) == 1
new[board] = new[board].replace(anchor, anchor + '''
  modify(HOST + 0xc2c0, (1u << 31) | (1u << 17), 0);''')
anchor = '  ret = usbhost_hub_initialize();'
new[board] = new[board].replace(anchor, '''  printf("K7 PHY: USB2=%08" PRIx32 " PIPE=%08" PRIx32
         " PHP=%08" PRIx32 "\\n", rd(HOST + 0xc200),
         rd(HOST + 0xc2c0), rd(0x26020038));
''' + anchor)
anchor = '#ifdef CONFIG_RK3576_USBHOST\n'
assert new[mmu].count(anchor) == 1
new[mmu] = new[mmu].replace(anchor, anchor + '''  MMU_REGION_FLAT_ENTRY("RK3576_PHP_GRF", 0x26020000, 0x1000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
''')
new[config] += '''
CONFIG_DEBUG_SCHED=y
CONFIG_DEBUG_SCHED_ERROR=y
CONFIG_BOARD_RESET_ON_ASSERT=1
'''
anchor = '  regval = xhci_oper_getreg(priv, XHCI_PORTSC(rhpndx));\n\n  /* A USB3'
assert new[core].count(anchor) == 1
new[core] = new[core].replace(anchor, '''  regval = xhci_oper_getreg(priv, XHCI_PORTSC(rhpndx));
  printf("K7 root port %d: reg=%" PRIxPTR " PORTSC=%08" PRIx32 "\\n",
         rhpndx, (uintptr_t)(priv->oper_base + XHCI_PORTSC(rhpndx)), regval);

  /* A USB3''')
work = root/'work/rk3576-usbhost'
backup = work/('pre-usb2-pipe-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
for p in paths:
    assert p.resolve() == p and p.is_file()
with tarfile.open(backup, 'w:gz') as tf:
    for p in paths: tf.add(p, arcname=str(p.relative_to(root)))
(work/'usb2-pipe-v4.patch').write_text(''.join(''.join(difflib.unified_diff(
    old[p].splitlines(True), new[p].splitlines(True),
    fromfile='a/'+str(p.relative_to(root)), tofile='b/'+str(p.relative_to(root)))) for p in paths))
try:
    for p in paths:
        assert p.read_text() == old[p]
        p.write_text(new[p])
except BaseException:
    for p in paths: p.write_text(old[p])
    raise
print('Backup:', backup)
print('Modified:', *relative)
