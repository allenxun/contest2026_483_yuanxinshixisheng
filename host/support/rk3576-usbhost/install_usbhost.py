#!/usr/bin/env python3
"""Experimental RK3576 xHCI backport. Preserve the legacy PCI driver files."""
from pathlib import Path
import datetime, hashlib, json, tarfile

root=Path('/home/swl/openvela'); n=root/'nuttx'; a=root/'apps'
w=root/'work/rk3576-usbhost'; ref=root/'work/rk3576-vision/reference/hub-upstream'
changed=['arch/arm64/src/rk3576/Kconfig','arch/arm64/src/rk3576/CMakeLists.txt',
         'arch/arm64/src/rk3576/Make.defs','arch/arm64/src/rk3576/rk3576_boot.c',
         'drivers/usbhost/Kconfig','drivers/usbhost/CMakeLists.txt',
         'drivers/usbhost/Make.defs','drivers/usbhost/usbhost_hub.c',
         'include/nuttx/usb/usbhost.h',
         'boards/arm64/rk3576/kickpi_k7/src/kickpi_k7_boardinit.c']
backup=w/('pre-usbhost-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.tgz')
with tarfile.open(backup,'w:gz') as tf:
    for f in changed: tf.add(n/f,arcname='nuttx/'+f)
def replace(path,old,new):
    s=path.read_text()
    if new in s:return
    assert s.count(old)==1,(str(path),old[:100])
    path.write_text(s.replace(old,new))

copies={
 'drivers/usbhost/usbhost_xhci.c':'drivers/usbhost/usbhost_xhci_rk3576.c',
 'drivers/usbhost/usbhost_xhci.h':'drivers/usbhost/usbhost_xhci_rk3576.h',
 'drivers/usbhost/usbhost_xhci_trace.c':'drivers/usbhost/usbhost_xhci_rk3576_trace.c',
 'drivers/usbhost/usbhost_xhci_trace.h':'drivers/usbhost/usbhost_xhci_rk3576_trace.h',
 'include/nuttx/usb/xhci.h':'include/nuttx/usb/xhci_rk3576.h'}
for src,dst in copies.items():
    s=(ref/src).read_text().replace('<nuttx/debug.h>','<debug.h>')
    s=s.replace('"usbhost_xhci.h"','"usbhost_xhci_rk3576.h"')
    s=s.replace('"usbhost_xhci_trace.h"','"usbhost_xhci_rk3576_trace.h"')
    s=s.replace('<nuttx/usb/xhci.h>','<nuttx/usb/xhci_rk3576.h>')
    if dst.endswith('usbhost_xhci_rk3576.c'):
        s=s.replace('up_addrenv_va_to_pa', 'k7_xhci_va_to_pa')
        s=s.replace('up_addrenv_pa_to_va', 'k7_xhci_pa_to_va')
        anchor='#include "usbhost_xhci_rk3576_trace.h"'
        s=s.replace(anchor,anchor+'''

/* This BSP is flat and maps all configured DRAM at identical VA/PA.
 * Keep conversion private to this experimental HCD, not a global arch stub.
 */
#ifndef CONFIG_BUILD_FLAT
#  error K7 xHCI requires the flat identity-mapped BSP
#endif
static uintptr_t k7_xhci_va_to_pa(const void *p) { return (uintptr_t)p; }
static void *k7_xhci_pa_to_va(uintptr_t p) { return (void *)p; }
''')
        # The camera's configuration is 613 bytes; NuttX enumeration does
        # not grow this control buffer. 512 would unconditionally fail.
        s=s.replace('#define XHCI_BUFSIZE             (512)',
                    '#define XHCI_BUFSIZE             (4096)')
        # Upstream's failed-initialize cleanup can free DMA memory while
        # the controller/worker is still active. This experimental adapter
        # allows one attempt per boot: preserve allocations until reset.
        old='''errout:
  xhci_mem_free(priv);
  kmm_free(conn);
  kmm_free(priv);

  return NULL;
}'''
        assert s.count(old)==1
        s=s.replace(old,'''errout:
  ops->irq_detach(arg);
  xhci_ctrl_halt(priv);
  uerr("K7 xHCI initialization failed; allocations retained until reset\\n");
  return NULL;
}''')
    (n/dst).write_text(s)

header=n/'include/nuttx/usb/usbhost.h'
replace(header,'  uint8_t speed;                        /* Device speed */',
'''  uint8_t speed;                        /* Device speed */
#ifdef CONFIG_USBHOST_RK3576_XHCI
  uint8_t nports;                       /* Downstream ports if this is a hub */
  uint8_t ttt;                          /* Transaction translator think time */
#endif''')
replace(header,'  FAR struct usbhost_devaddr_s *pdevgen; /* Address generation data pointer */',
'''  FAR struct usbhost_devaddr_s *pdevgen; /* Address generation data pointer */
#ifdef CONFIG_USBHOST_RK3576_XHCI
  uint8_t bus;
#endif''')
hub=n/'drivers/usbhost/usbhost_hub.c'
replace(hub,'  priv->ctrlcurrent = hubdesc->ctrlcurrent;',
'''  priv->ctrlcurrent = hubdesc->ctrlcurrent;
#ifdef CONFIG_USBHOST_RK3576_XHCI
  hport->nports = hubdesc->nports;
  hport->ttt = (hubchar & USBHUB_CHAR_TTTT_MASK) >> USBHUB_CHAR_TTTT_SHIFT;
  syslog(LOG_INFO, "K7 HUB: addr=%u ports=%u speed=%u\\n",
         hport->funcaddr, hport->nports, hport->speed);
#endif''')
replace(hub,'#include <debug.h>','#include <debug.h>\n#include <syslog.h>')
# Add multiple-TT high-speed hubs alongside the existing FS/single-TT ids.
replace(hub,'static const struct usbhost_id_s g_id[2] =','static const struct usbhost_id_s g_id[3] =')
needle='''      1,              /* proto HS hub */
      0,              /* vid          */
      0               /* pid          */
  }'''
replace(hub,needle,needle+''',
  { USB_CLASS_HUB, 0, 2, 0, 0 }''')
replace(hub,'  2,                      /* nids     */','  3,                      /* nids     */')
# Avoid dereferencing a class after its disconnected callback freed it.
replace(hub,'''                  CLASS_DISCONNECTED(connport->devclass);

                  if (connport->devclass->connect == usbhost_connect)''',
'''                  bool ishub = connport->devclass->connect == usbhost_connect;
                  CLASS_DISCONNECTED(connport->devclass);

                  if (ishub)''')

k=n/'drivers/usbhost/Kconfig'
replace(k,'menuconfig USBHOST_XHCI_PCI', '''config USBHOST_RK3576_XHCI
	bool "Experimental K7 memory-mapped xHCI host"
	depends on ARCH_CHIP_RK3576 && USBHOST_WAITER && SCHED_HPWORK && SCHED_LPWORK
	depends on !USBHOST_XHCI_PCI
	select USBHOST_HAVE_ASYNCH
	default n

config USBHOST_XHCI_ENUM_RETRIES
	int
	default 3
	depends on USBHOST_RK3576_XHCI

menuconfig USBHOST_XHCI_PCI''')
replace(k,'if USBHOST_XHCI_PCI\n','if USBHOST_XHCI_PCI || USBHOST_RK3576_XHCI\n')
replace(n/'drivers/usbhost/CMakeLists.txt','  # HCD debug/trace logic',
'''  if(CONFIG_USBHOST_RK3576_XHCI)
    list(APPEND SRCS usbhost_xhci_rk3576.c usbhost_xhci_rk3576_trace.c)
  endif()

  # HCD debug/trace logic''')
replace(n/'drivers/usbhost/Make.defs','# HCD debug/trace logic',
'''ifeq ($(CONFIG_USBHOST_RK3576_XHCI),y)
CSRCS += usbhost_xhci_rk3576.c usbhost_xhci_rk3576_trace.c
endif

# HCD debug/trace logic''')
replace(n/'arch/arm64/src/rk3576/Kconfig','endmenu',
'''config RK3576_USBHOST
	bool "K7 USB2 host bring-up"
	depends on USBHOST_RK3576_XHCI && ARCH_BOARD_KICKPI_K7 && BUILD_FLAT
	select RK3576_USB_DIAG
	default n

endmenu''')
replace(n/'arch/arm64/src/rk3576/CMakeLists.txt','target_sources(arch PRIVATE ${SRCS})',
'''if(CONFIG_RK3576_USBHOST)
  list(APPEND SRCS rk3576_usbhost.c)
endif()

target_sources(arch PRIVATE ${SRCS})''')
replace(n/'arch/arm64/src/rk3576/Make.defs','CHIP_CSRCS += rk3576_serial.c',
'''CHIP_CSRCS += rk3576_serial.c
ifeq ($(CONFIG_RK3576_USBHOST),y)
CHIP_CSRCS += rk3576_usbhost.c
endif''')
replace(n/'arch/arm64/src/rk3576/rk3576_boot.c','  MMU_REGION_FLAT_ENTRY("DRAM0_S0",',
'''#ifdef CONFIG_RK3576_USBHOST
  MMU_REGION_FLAT_ENTRY("RK3576_USB2PHY", 0x2602e000, 0x4000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
  MMU_REGION_FLAT_ENTRY("RK3576_PMU_CRU", 0x27220000, 0x10000,
                        MT_DEVICE_NGNRNE | MT_RW | MT_SECURE),
#endif

  MMU_REGION_FLAT_ENTRY("DRAM0_S0",''')
(n/'arch/arm64/src/rk3576/rk3576_usbhost.c').write_bytes((w/'rk3576_usbhost.c').read_bytes())
board=n/'boards/arm64/rk3576/kickpi_k7/src/kickpi_k7_boardinit.c'
if 'int board_reset(int status)' not in board.read_text():
    board.write_text(board.read_text()+'''
#ifdef CONFIG_BOARDCTL_RESET
#include <nuttx/arch.h>
#include <errno.h>
int board_reset(int status)
{
  up_systemreset();
  return -EIO;
}
#endif
''')
app=a/'examples/k7host';app.mkdir(exist_ok=True)
(app/'k7host_main.c').write_bytes((w/'k7host_main.c').read_bytes())
(app/'Kconfig').write_text('config EXAMPLES_K7HOST\n\tbool "K7 USB host enumeration command"\n\tdepends on RK3576_USBHOST\n')
(app/'CMakeLists.txt').write_text('if(CONFIG_EXAMPLES_K7HOST)\n  nuttx_add_application(NAME k7host SRCS k7host_main.c STACKSIZE 8192 PRIORITY 100)\nendif()\n')
(app/'Make.defs').write_text('ifneq ($(CONFIG_EXAMPLES_K7HOST),)\nCONFIGURED_APPS += $(APPDIR)/examples/k7host\nendif\n')
(app/'Makefile').write_text('include $(APPDIR)/Make.defs\nPROGNAME = k7host\nPRIORITY = 100\nSTACKSIZE = 8192\nMODULE = $(CONFIG_EXAMPLES_K7HOST)\nMAINSRC = k7host_main.c\ninclude $(APPDIR)/Application.mk\n')
config=n/'boards/arm64/rk3576/kickpi_k7/configs/usbenum';config.mkdir(exist_ok=True)
(config/'defconfig').write_bytes((config.parent/'usbdiag/defconfig').read_bytes()+b'''
CONFIG_USBHOST=y
CONFIG_USBHOST_WAITER=y
CONFIG_USBHOST_WAITER_STACKSIZE=8192
CONFIG_SCHED_LPWORK=y
CONFIG_SCHED_LPWORKSTACKSIZE=8192
CONFIG_SCHED_HPWORKSTACKSIZE=8192
CONFIG_USBHOST_RK3576_XHCI=y
CONFIG_USBHOST_XHCI_MAX_DEVS=8
CONFIG_USBHOST_HUB=y
CONFIG_RK3576_USBHOST=y
CONFIG_EXAMPLES_K7HOST=y
CONFIG_ARM64_HAVE_PSCI=y
CONFIG_ARM64_PSCI=y
CONFIG_BOARDCTL_RESET=y
CONFIG_DEBUG_USB=y
CONFIG_DEBUG_USB_ERROR=y
CONFIG_DEBUG_USB_WARN=y
''')
provenance={'upstream_repo':'Fishwaldo/nuttx','upstream_commit':'25e387ffedc9f2b746df975f731ee4fdbb464a7a',
 'review':'https://github.com/apache/nuttx/pull/19862','status':'experimental backport, not an upstream release',
 'copied_files':copies,'local_adjustments':['private filenames preserve PCI driver','debug header compatibility','4096-byte control buffers','retain DMA allocations on failed startup until reset','minimal hub metadata and disconnect lifetime fix'],
 'backup':str(backup)}
(w/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps(provenance,indent=2))
