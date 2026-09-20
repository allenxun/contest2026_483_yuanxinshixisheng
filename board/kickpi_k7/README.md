# KICKPI-K7 / RK3576 initial openvela BSP

This port targets one Cortex-A53 core, a flat AArch64 address space, GICv2,
the architectural timer and UART0 using NuttX's generic 16550 driver.
DDR initialization, clocks, pinmux, TF-A and OP-TEE remain supplied by the
board's existing Rockchip loader and U-Boot.

## Build

Source baseline: NuttX `e987a81c32cab008d1a8521669e5488d00271322` inside
the existing `/home/swl/openvela` multi-repository checkout.

```sh
cd /home/swl/openvela
./build.sh kickpi_k7:nsh --cmake -b /home/swl/openvela/cmake_out/rk3576_bringup -j6
python3 work/rk3576-bringup/verify_image.py cmake_out/rk3576_bringup
```

Use a new build directory after changing the board defconfig, or explicitly
update the installed configuration. The wrapper can reuse an older `.config`.
The initial build log's `kpi_k7:nsh/defconfig` grep diagnostic is a wrapper
path-parsing issue; use the final build status and artifact verifier.

## Memory and UART

| Item | Value |
| --- | --- |
| Image load address / ELF entry | `0x40400000` |
| ARM64 Image text offset | `0` |
| NuttX RAM end, exclusive | `0x48200000` |
| Live U-Boot device tree | `0x48300000` |
| OP-TEE/firmware memory gap | `0x48400000`–`0x49400000` |
| UART0 | `0x2ad40000`, 1500000 baud, 8N1 |
| UART register access / stride | 32 bits / 4 bytes |
| UART interrupt | SPI 76, NuttX IRQ 108 |
| GIC distributor / CPU interface | `0x2a701000` / `0x2a702000` |
| Implemented GIC interrupt IDs | 512 (GICD_TYPER read on this board) |

`CONFIG_16550_REGINCR=1` with `CONFIG_16550_REGWIDTH=32` produces a four-byte
stride. `CONFIG_16550_SUPRESS_CONFIG=y` preserves U-Boot's UART setup;
the nominal 24 MHz configuration value is not used to rewrite the divisor.

## RAM download and boot

The tested board has U-Boot 2017.09 dated 2026-05-26 and exposes Fastboot
USB serial `f71a9d152132db55`, VID:PID `18d1:4d00`. It has no serial
`loadb` or `loady` command. UART is `/dev/ttyUSB0` in Ubuntu.

1. Interrupt boot with Ctrl-C to obtain `=>`.
2. Run `fastboot usb 0`; attach the Google USB download gadget to Ubuntu
   in VMware if it was re-enumerated after a reboot.
3. Stage the raw `nuttx.bin` using Fastboot `download` followed by `continue`.
   The provided Python helper checks the exact USB serial and image format,
   captures UART, and implements no flash or erase commands.
4. Verify the downloaded image at `0x40c00800` using `md.l` and `crc32`.
   This buffer address comes from Rockchip's RK3576 configuration and was
   confirmed by matching the header and complete image CRC on this K7.
5. Copy exactly the image's byte count to `0x40400000` using `cp.b`, then
   verify the CRC again. U-Boot counts and addresses here are hexadecimal.
6. Capture serial before running `booti 40400000 - 48300000`.

An ordinary inline FIT passed to Fastboot `boot` failed in the vendor
`board_do_bootm` DTB loader. The RAM staging route uses the available raw
ARM64 `booti` command with the board's already-loaded DTB.

No persistent flash operation is part of this procedure. A cold power cycle
restores the existing boot chain; after an early kernel failure, U-Boot's
attempted reset may hang and require that power cycle.

In the configured Ubuntu VM, the automated equivalent is:

```sh
cd /home/swl/openvela/work/rk3576-bringup
export PYTHONPATH="$PWD/host-tools/root/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
python3 ramboot_k7.py /home/swl/openvela/cmake_out/rk3576_bringup \
  --serial f71a9d152132db55 --log ramboot.log
python3 validate_nsh.py --log nsh-check.log --json nsh-check.json
```

The first command requires U-Boot already in Fastboot. The second requires
NSH already running and checks the final board configuration. Python 3,
`pyserial`, `pyusb` and libusb are required. In this VM, pyserial is installed
and pyusb was extracted under `host-tools/root` without changing system packages.
Release-package users can pass its `firmware` directory as the build argument.

If VMware shows the device connected but Ubuntu `lsusb` does not list
`18d1:4d00`, disconnect/reconnect that gadget in VMware. Preserve power and
the USB-TTL connection when replugging the independent USB-C data cable.

## EL2 handoff fix

This K7 handed the Image `HCR_EL2=0x08000032`. Bit 27 (TGE) makes an
exception return to EL1 illegal. The generic NuttX initialization only
ORs in RW, preserving TGE. The RK3576 early hook establishes `HCR_EL2.RW=1`
with the inherited trap and stage-2 controls clear, and initializes SCTLR_EL1
with its MMU off. The subsequent generic EL2-to-EL1 initialization then works.
The early diagnostic retains the incoming HCR/SCTLR values in the boot log.

The board app initialization mounts procfs on `/proc`, allowing `ps` and
`free` to work immediately at the first NSH prompt.

## Scope

This is an initial board bring-up. SMP, eMMC/SD drivers, USB camera,
networking, NPU acceleration, STM32 communication and application-level AI
are separate work. Compilation and an early UART banner alone do not prove
that NSH, interrupt-driven input or the scheduler work.

Hardware validation results are recorded with the delivered logs and report.
The CH340/VMware link at 1500000 baud has occasionally dropped portions of
long output bursts in both U-Boot and NSH. Short command responses and full
`ps` output have been captured successfully; this is not a long-duration
serial reliability qualification.

## References

- [Rockchip RK3576 U-Boot configuration](https://github.com/rockchip-linux/u-boot/blob/next-dev/configs/rk3576_defconfig)
- [Rockchip ARM64 booti](https://github.com/rockchip-linux/u-boot/blob/next-dev/cmd/booti.c)
- [Rockchip Fastboot transport](https://github.com/rockchip-linux/u-boot/blob/next-dev/drivers/usb/gadget/f_fastboot.c)
- [KICKPI-K7 quick start](https://doc.kickpi.cn/Products/Beginner-Guide/KICKPI-K7/)
- Board-specific memory, UART and interrupt facts were checked against
  `/home/swl/k7-dt/k7-live.dts` and the live U-Boot console.
