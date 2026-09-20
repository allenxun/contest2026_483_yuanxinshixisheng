/* SPDX-License-Identifier: Apache-2.0 */
/* K7 USB-A / RK3576 DWC3 host bring-up, initially USB2-only.
 * Register facts from Rockchip's rk3576.dtsi, clk-rk3576.c,
 * phy-rockchip-inno-usb2.c and gpio-rockchip.c. See work provenance.
 * DRAM, PHP power domain and parent PLLs must be initialized by U-Boot.
 */
#include <nuttx/config.h>
#include <nuttx/arch.h>
#include <nuttx/irq.h>
#include <nuttx/mutex.h>
#include <nuttx/usb/usbhost.h>
#include <nuttx/usb/xhci_rk3576.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdint.h>

#define HOST 0x23400000ul
#define PHY  0x26030000ul
#define IRQ  292

static mutex_t g_lock = NXMUTEX_INITIALIZER;
static struct usbhost_connection_s *g_connection;
static int g_attempted;

static uint32_t rd(uintptr_t p) { return *(volatile uint32_t *)p; }
static void wr(uintptr_t p, uint32_t v) { *(volatile uint32_t *)p = v; }
static void maskwrite(uintptr_t p, uint32_t mask, uint32_t v)
{
  wr(p, (mask << 16) | (v & mask));
}
static void modify(uintptr_t p, uint32_t clear, uint32_t set)
{
  wr(p, (rd(p) & ~clear) | set);
}

static int attach(void *arg, xcpt_t handler, void *priv)
{
  int ret = irq_attach(IRQ, handler, priv);
  if (ret == 0) up_enable_irq(IRQ);
  return ret;
}
static void detach(void *arg)
{
  up_disable_irq(IRQ);
  irq_detach(IRQ);
}
static bool dmacapable(void *arg, uint8_t *p, size_t n)
{
  uintptr_t address = (uintptr_t)p;
  uintptr_t end = CONFIG_RAM_START + CONFIG_RAM_SIZE;
  return address >= CONFIG_RAM_START && address < end && n <= end - address;
}
static const struct xhci_bus_ops_s g_ops = {attach, detach, dmacapable};

int rk3576_usbhost_initialize(void)
{
  int ret = nxmutex_lock(&g_lock);
  uint32_t id;
  uint32_t cap;
  if (ret < 0) return ret;
  if (g_connection) { nxmutex_unlock(&g_lock); return 0; }
  if (g_attempted) { nxmutex_unlock(&g_lock); return -EALREADY; }

  /* A reset is required after a failed attempt. No retry may reuse DMA. */
  g_attempted = 1;
  if (!(rd(0x27380570) & (1u << 9)) ||
      ((rd(0x27380128) | rd(0x27380120)) & (1u << 15)))
    {
      puts("K7 host: PHP power/bus prerequisite missing; no host MMIO accessed.");
      ret = -EHOSTDOWN;
      goto out;
    }

  /* Ungate only GPIO3, PHP root, OTG1 and its USB2 PHY AXI clocks. */
  maskwrite(0x27200848, 1u << 3, 0);
  maskwrite(0x27200888, 1u << 7, 0);
  maskwrite(0x2720088c, (7u << 3) | (1u << 14), 0);
  maskwrite(0x27200890, 1u, 0);
  maskwrite(0x27220a00, 1u << 10, 0); /* PHY1 GRF APB reset */
  maskwrite(0x27200a8c, 1u << 3, 0);  /* DWC3 OTG1 reset */

  /* K7 vcc5v0-host: GPIO3_PD6, pinmux GPIO, active high. */
  maskwrite(0x2ae30004, 1u << 14, 1u << 14); /* DR high half */
  maskwrite(0x2ae3000c, 1u << 14, 1u << 14); /* DDR high half */
  maskwrite(0x2604407c, 0x0f00, 0);          /* GPIO3_D6 mux */

  id = rd(HOST + 0xc120);
  if ((id >> 16) != 0x5533)
    {
      printf("K7 host: unexpected DWC3 id %08" PRIx32 "\n", id);
      ret = -ENODEV;
      goto out;
    }

  /* Hold the controller/PHY interface while preparing the USB2 analog PHY.
   * USB3 is not initialized. Select Rockchip's USB2-only PIPE status
   * override, then release both controller PHY-interface reset bits.
   * Source: rk3576_phy_cfgs[1].pipe_phystatus and property_enable(true)
   * in Rockchip develop-6.1 phy-rockchip-inno-usb2.c (0x0038, 0x0189).
   * Holding PHYSOFTRST indefinitely is not a USB3 disable mechanism.
   */
  modify(HOST + 0xc110, 0, 1u << 11);
  modify(HOST + 0xc200, 0, 1u << 31);
  modify(HOST + 0xc2c0, 0, 1u << 31);
  /* RK3576 also requires Combo PHY USB mode when SuperSpeed is disabled.
   * Rockchip U-Boot rockchip_combphy_usb3_init() explicitly applies
   * usb_mode_set in its dis-u3otg1-port path. No USB3 analog setup here.
   */
  maskwrite(0x27208800, (1u << 2) | (1u << 7), 0); /* PHY1 APB clocks */
  maskwrite(0x27208a00, 1u << 7, 0); /* PHY1 APB reset */
  printf("K7 Combo mode before=%08" PRIx32 "\n", rd(0x2602a000));
  maskwrite(0x2602a000, 0x3f, 0x04);
  printf("K7 Combo mode after=%08" PRIx32 "\n", rd(0x2602a000));
  maskwrite(0x26020038, 0xffff, 0x0189); /* USB2-only PIPE override */

  maskwrite(PHY + 0x10, 1u << 13, 0); /* Analog SIDDQ off */
  maskwrite(0x27220a04, 1u << 8, 1u << 8);
  up_udelay(10);
  maskwrite(0x27220a04, 1u << 8, 0);
  up_udelay(200);
  maskwrite(PHY + 0x0c, 0x0f00, 0x0900); /* HS voltage trim */
  maskwrite(PHY + 0x10, 0x0018, 0x0010); /* Pre-emphasis */
  maskwrite(PHY + 0x00, 0x0600, 0x0200); /* Force ID low */
  maskwrite(PHY + 0x08, 1u, 0);          /* 480 MHz clock */
  maskwrite(PHY + 0x00, 0x01ff, 0);      /* Exit suspend */
  up_mdelay(2);

  /* K7 uses a 16-bit UTMI interface. Honor the DT's no-freeclk/no-SLPM
   * and park-mode quirks. Keep USB2 PHY awake for first bring-up.
   */
  modify(HOST + 0xc200,
         (1u << 30) | (1u << 8) | (1u << 6) | (1u << 4) | (15u << 10),
         (1u << 3) | (5u << 10));
  modify(HOST + 0xc11c, 0, (1u << 28) | (1u << 17) | (1u << 16));
  modify(HOST + 0xc110, 3u << 12, 1u << 12); /* Host mode */
  up_mdelay(100);
  modify(HOST + 0xc200, 1u << 31, 0);
  modify(HOST + 0xc2c0, (1u << 31) | (1u << 17), 0);
  up_mdelay(100);
  modify(HOST + 0xc110, 1u << 11, 0);
  up_mdelay(100);

  cap = rd(HOST);
  if ((cap & 0xff) < 0x20 || (cap & 0xff) > 0x80 ||
      ((cap & 0xff) & 3) || (cap >> 16) < 0x90 || (cap >> 16) > 0x120)
    {
      printf("K7 host: invalid xHCI capability %08" PRIx32 "\n", cap);
      ret = -ENODEV;
      goto out;
    }

  printf("K7 host: DWC3=%08" PRIx32 " GCTL=%08" PRIx32
         " xHCI=%08" PRIx32 " PHY=%08" PRIx32 "\n",
         id, rd(HOST + 0xc110), cap, rd(PHY));
  printf("K7 PHY: USB2=%08" PRIx32 " PIPE=%08" PRIx32
         " PHP=%08" PRIx32 "\n", rd(HOST + 0xc200),
         rd(HOST + 0xc2c0), rd(0x26020038));
  ret = usbhost_hub_initialize();
  if (ret < 0) goto out;
#ifdef CONFIG_USBHOST_MSC
  ret = usbhost_msc_initialize();
  if (ret < 0) goto out;
#endif
  g_connection = xhci_initialize("k7-usb-a", 0, HOST, &g_ops, NULL);
  ret = g_connection ? 0 : -EIO;
out:
  nxmutex_unlock(&g_lock);
  return ret;
}
