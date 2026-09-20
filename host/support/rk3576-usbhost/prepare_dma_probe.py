from pathlib import Path
import datetime, difflib, tarfile
root = Path('/home/swl/openvela')
paths = [root/'nuttx/drivers/usbhost/usbhost_xhci_rk3576.c', root/'nuttx/boards/arm64/rk3576/kickpi_k7/configs/usbenum/defconfig']
old = {p:p.read_text() for p in paths}
new = dict(old)
core, config = paths
for tag in ['CMD timeout', 'REGS:', 'EVENT:', 'DMA:', 'EVT%d', 'CMD0']:
    anchor = 'printf("K7 '+tag
    assert new[core].count(anchor) == 1
    new[core] = new[core].replace(anchor, 'uerr("K7 '+tag)
anchor = '      /* Check for missed interrupts */'
assert new[core].count(anchor) == 1
new[core] = new[core].replace(anchor, '''      uerr("K7 BUS: CFG0=%08" PRIx32 " CFG1=%08" PRIx32 "\\n",
           xhci_capa_getreg(priv, 0xc100), xhci_capa_getreg(priv, 0xc104));
      uerr("K7 HI: CRCR=%08" PRIx32 " DCBAA=%08" PRIx32
           " ERST=%08" PRIx32 " ERDP=%08" PRIx32 "\\n",
           xhci_oper_getreg(priv, XHCI_CRCR + 4),
           xhci_oper_getreg(priv, XHCI_DCBAAP + 4),
           xhci_runt_getreg(priv, XHCI_ERSTBA(0) + 4),
           xhci_runt_getreg(priv, XHCI_ERDP(0) + 4));
      struct xhci_event_ring_s *table = (void *)priv->pg_erst;
      uerr("K7 ERST0: base=%016" PRIx64 " size=%" PRIu32 "\\n",
           table->base, table->size);
''' + anchor)
new[config] += '\n# Temporary A/B experiment: isolate CPU cache visibility from DMA.\nCONFIG_ARM64_DCACHE_DISABLE=y\n'
work=root/'work/rk3576-usbhost'
backup=work/('pre-dma-probe-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
with tarfile.open(backup,'w:gz') as tf:
    for p in paths:
        assert p.resolve()==p
        tf.add(p,arcname=str(p.relative_to(root)))
(work/'dma-probe-v6.patch').write_text(''.join(''.join(difflib.unified_diff(old[p].splitlines(True),new[p].splitlines(True),fromfile='a/'+str(p.relative_to(root)),tofile='b/'+str(p.relative_to(root)))) for p in paths))
for p in paths: assert p.read_text()==old[p]
for p in paths: p.write_text(new[p])
print(backup)
