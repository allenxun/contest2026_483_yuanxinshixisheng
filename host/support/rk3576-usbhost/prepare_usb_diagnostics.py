from pathlib import Path
import datetime
import difflib
import tarfile

root = Path('/home/swl/openvela')
paths = [root/'nuttx/drivers/serial/uart_16550.c',
         root/'nuttx/boards/arm64/rk3576/kickpi_k7/configs/usbenum/defconfig']
old = {p: p.read_text() for p in paths}
new = dict(old)
uart, config = paths
anchor = '  u16550_putc(priv, ch);\n}'
assert new[uart].count(anchor) == 1
new[uart] = new[uart].replace(anchor, '''  u16550_putc(priv, ch);
#ifdef CONFIG_RK3576_USBHOST
  /* Temporary K7 bring-up pacing: preserve crash diagnostics through the
   * 1.5 Mbaud CH340/VMware link. Normal UART transfers are unchanged.
   */
  up_udelay(50);
#endif
}''')
assert 'CONFIG_DEBUG_ASSERTIONS_EXPRESSION=y' not in new[config]
new[config] += '\nCONFIG_DEBUG_ASSERTIONS_EXPRESSION=y\n'
work = root/'work/rk3576-usbhost'
backup = work/('pre-diagnostics-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
for p in paths:
    assert p.resolve() == p and p.is_file()
with tarfile.open(backup, 'w:gz') as tf:
    for p in paths:
        tf.add(p, arcname=str(p.relative_to(root)))
(work/'diagnostics-v3.patch').write_text(''.join(''.join(difflib.unified_diff(
    old[p].splitlines(True), new[p].splitlines(True),
    fromfile='a/'+str(p.relative_to(root)), tofile='b/'+str(p.relative_to(root)))) for p in paths))
try:
    for p in paths:
        assert p.read_text() == old[p]
        p.write_text(new[p])
except BaseException:
    for p in paths:
        p.write_text(old[p])
    raise
print('Backup:', backup)
print('Updated:', *paths)
