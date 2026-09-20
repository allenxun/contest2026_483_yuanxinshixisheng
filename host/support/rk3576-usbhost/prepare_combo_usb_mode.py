from pathlib import Path
import datetime,tarfile,difflib
root=Path('/home/swl/openvela')
paths=[root/'nuttx/arch/arm64/src/rk3576/rk3576_usbhost.c',root/'nuttx/arch/arm64/src/rk3576/rk3576_boot.c']
old={p:p.read_text() for p in paths};new=dict(old)
board,mmu=paths
anchor='  maskwrite(0x26020038, 0xffff, 0x0189); /* USB2-only PIPE override */'
assert new[board].count(anchor)==1
new[board]=new[board].replace(anchor,'''  /* RK3576 also requires Combo PHY USB mode when SuperSpeed is disabled.
   * Rockchip U-Boot rockchip_combphy_usb3_init() explicitly applies
   * usb_mode_set in its dis-u3otg1-port path. No USB3 analog setup here.
   */
  maskwrite(0x27208800, (1u << 2) | (1u << 7), 0); /* PHY1 APB clocks */
  maskwrite(0x27208a00, 1u << 7, 0); /* PHY1 APB reset */
  printf("K7 Combo mode before=%08" PRIx32 "\\n", rd(0x2602a000));
  maskwrite(0x2602a000, 0x3f, 0x04);
  printf("K7 Combo mode after=%08" PRIx32 "\\n", rd(0x2602a000));
'''+anchor)
anchor='#ifdef CONFIG_RK3576_USBHOST\n'
assert new[mmu].count(anchor)==1
new[mmu]=new[mmu].replace(anchor,anchor+'''  MMU_REGION_FLAT_ENTRY("RK3576_COMBOPHY1_GRF", 0x2602a000, 0x2000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
''')
work=root/'work/rk3576-usbhost'
backup=work/('pre-combo-mode-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
with tarfile.open(backup,'w:gz') as tf:
 for p in paths:
  assert p.resolve()==p;tf.add(p,arcname=str(p.relative_to(root)))
(work/'combo-mode-v8.patch').write_text(''.join(''.join(difflib.unified_diff(old[p].splitlines(True),new[p].splitlines(True),fromfile='a/'+str(p.relative_to(root)),tofile='b/'+str(p.relative_to(root)))) for p in paths))
for p in paths:assert p.read_text()==old[p]
for p in paths:p.write_text(new[p])
print(backup)
