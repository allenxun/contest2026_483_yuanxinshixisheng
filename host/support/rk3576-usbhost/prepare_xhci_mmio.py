from pathlib import Path
import datetime, difflib, tarfile
root = Path('/home/swl/openvela')
p = root/'nuttx/drivers/usbhost/usbhost_xhci_rk3576.c'
old = p.read_text()
new = old
anchor = '  *((FAR volatile uint64_t *)addr) = value;'
assert new.count(anchor) == 2
new = new.replace(anchor, '''  /* Match xHCI's low-dword then high-dword pointer register access.
   * Rockchip Linux xhci_write_64() uses lo_hi_writeq(), including ARM64.
   */
  *((FAR volatile uint32_t *)addr) = (uint32_t)value;
  *((FAR volatile uint32_t *)(addr + 4)) = (uint32_t)(value >> 32);
  __asm__ __volatile__("dsb sy" ::: "memory");''')
anchor = 'static void *k7_xhci_pa_to_va(uintptr_t p) { return (void *)p; }'
assert new.count(anchor) == 1
new = new.replace(anchor, anchor+'\nstatic volatile uint32_t g_k7_irq_count;\n')
anchor = '  /* Get pending interrupts */\n\n  priv->pending ='
assert new.count(anchor) == 1
new = new.replace(anchor, '  g_k7_irq_count++;\n\n'+anchor)
anchor = '  xhci_door_putreg(priv, XHCI_DOORBEL(0), 0);'
assert new.count(anchor) == 1
new = new.replace(anchor, '  __asm__ __volatile__("dsb sy" ::: "memory");\n'+anchor)
anchor = '      /* Check for missed interrupts */\n\n      xhci_events_poll(priv);'
assert new.count(anchor) == 1
new = new.replace(anchor, '''      /* Check for missed interrupts */

      xhci_events_poll(priv);
      printf("K7 CMD timeout: ret=%d irq=%" PRIu32 " op=%" PRIxPTR
             " rt=%" PRIxPTR " db=%" PRIxPTR "\\n", ret, g_k7_irq_count,
             priv->oper_base, priv->runt_base, priv->door_base);
      printf("K7 REGS: STS=%08" PRIx32 " CRCR=%08" PRIx32
             " DCBAA=%08" PRIx32 " CONFIG=%08" PRIx32 "\\n",
             xhci_oper_getreg(priv, XHCI_USBSTS),
             xhci_oper_getreg(priv, XHCI_CRCR),
             xhci_oper_getreg(priv, XHCI_DCBAAP),
             xhci_oper_getreg(priv, XHCI_CONFIG));
      printf("K7 EVENT: IMAN=%08" PRIx32 " SIZE=%08" PRIx32
             " BA=%08" PRIx32 " DP=%08" PRIx32 "\\n",
             xhci_runt_getreg(priv, XHCI_IMAN(0)),
             xhci_runt_getreg(priv, XHCI_ERSTSZ(0)),
             xhci_runt_getreg(priv, XHCI_ERSTBA(0)),
             xhci_runt_getreg(priv, XHCI_ERDP(0)));
      printf("K7 DMA: cmd=%p erst=%p event=%p i=%u c=%u\\n",
             priv->cmd.ring, priv->pg_erst, priv->evnt.ring,
             priv->evnt.i, priv->evnt.ccs);
      for (int k = 0; k < 4; k++)
        printf("K7 EVT%d %016" PRIx64 " %08" PRIx32 " %08" PRIx32 "\\n",
               k, priv->evnt.ring[k].d0, priv->evnt.ring[k].d1,
               priv->evnt.ring[k].d2);
      printf("K7 CMD0 %016" PRIx64 " %08" PRIx32 " %08" PRIx32 "\\n",
             priv->cmd.ring[0].d0, priv->cmd.ring[0].d1, priv->cmd.ring[0].d2);''')
work = root/'work/rk3576-usbhost'
backup = work/('pre-mmio-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
assert p.resolve() == p
with tarfile.open(backup, 'w:gz') as tf: tf.add(p, arcname=str(p.relative_to(root)))
(work/'xhci-mmio-v5.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+str(p.relative_to(root)),tofile='b/'+str(p.relative_to(root)))))
assert p.read_text() == old
p.write_text(new)
print('Backup:', backup)
