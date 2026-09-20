# K7 openvela 云台控制程序

当前状态：**新版已通过 RAM 下载运行在真实 K7 上，用户在第二次测试后确认“动了”。openvela → UART6 → STM32 → 云台控制链路已打通。** UART6 内部回环通过，`/dev/ttyS1` 和 `gimbal` 命令已实机验证；两次 `gimbal test 20` 均完成并正常返回，最后发送目标 (0,0)。原协议没有 MCU 应答，运动确认来自用户观察；尚未测量角度、精度或分别验收两个轴的性能。

12 项主机协议/伪终端检查及镜像入口、内存布局、下载前后 CRC 校验通过。首次实机测试从命令发送到 NSH 返回约 3.71 秒，测试后 `ps` 正常。

## 接线与串口

| K7 40Pin | STM32 |
|---|---|
| Pin 5 / UART6 TX / GPIO4_A4 | USART3 RX，现有源码为 PC11 |
| Pin 7 / UART6 RX / GPIO4_A6 | USART3 TX，现有源码为 PC10 |
| Pin 6 / GND | GND |

业务口为 openvela `/dev/ttyS1`，固定 115200、8N1、无流控。它是物理 UART6，软件设备名不是 `/dev/ttyS6`。调试口 UART0 保持 1500000，Ubuntu 仍通过 `/dev/ttyUSB0` 进入 NSH。

## 加载新版之后，在 nsh> 输入

现在可以在 Ubuntu 重新打开串口：

```sh
python3 -m serial.tools.miniterm /dev/ttyUSB0 1500000 --raw --eol CR
```

按回车出现 `nsh>` 后输入以下命令。若 K7 断电，本次 RAM 镜像会丢失，需要重新加载。

```text
gimbal info
gimbal frame 10 -10
gimbal zero
gimbal set 20 0
gimbal set 0 20
gimbal zero
gimbal test 20
```

`frame` 只预览二进制帧，不发送。`set X Y [MS]` 在默认 300ms 内以每秒 50 对的频率发送 X/Y 目标；可指定 20～10000ms。目标值限制为 X=-250～250、Y=-200～200，沿用原项目的单位，**不是角度**。

`test [A]` 默认幅度 20，可选 1～50。依次发送 (0,0)、(A,0)、(-A,0)、(0,0)、(0,A)、(0,-A)、(0,0)，每个目标持续发送 500ms，约 3.5 秒后退出。

`zero` 发送位置目标 (0,0)，不是电机断电或急停命令。命令退出后，MCU 是否继续保持目标由现有 MCU 固件决定。

原协议没有应答包；`TX complete` 表示发送调用完成，不表示 MCU 已收到或云台已移动。初始化内部回环也只验证 UART 外设，不验证外部引脚与 MCU。

## 协议

每轴 7 字节：`55 AA axis low high 00 FA`。axis=00 为 X，axis=FF 为 Y；目标是有符号 16 位小端数。例如 X=10、Y=-10：

```text
55 AA 00 0A 00 00 FA
55 AA FF F6 FF 00 FA
```

程序处理部分写入、写入超时和参数错误，同一固件中不允许同时运行两个 gimbal 发送任务。二进制串口不进行换行转换。

## 源码与编译

Ubuntu 源码：

- `/home/swl/openvela/apps/examples/gimbal/gimbal_main.c`
- `/home/swl/openvela/nuttx/arch/arm64/src/rk3576/rk3576_uart6.c`
- `/home/swl/openvela/nuttx/boards/arm64/rk3576/kickpi_k7/configs/nsh/defconfig`

```sh
cd /home/swl/openvela
./build.sh kickpi_k7:nsh --cmake -b /home/swl/openvela/cmake_out/rk3576_gimbal_uart6 -j6
python3 work/rk3576-bringup/verify_image.py cmake_out/rk3576_gimbal_uart6
```

本次同时修复了 RK3576 芯片 Kconfig 未接入架构 Kconfig 的问题。此前 UART0 依靠通用 16550 配置启动；本次显式启用 RK3576_UART0/RK3576_UART6。

UART6 基址 0x2AD90000；SPI82 对应 GIC IRQ114。使用 32 位访问、4 字节寄存器间距。CRU 选择 24MHz 时钟、UART 整数分频 13，实际约 115384.6 baud，偏差 +0.16%。只修改 UART6 对应的时钟/复位位、GPIO4_A4/A6 引脚复用和上下拉位。

保留全局 16550 SUPRESS_CONFIG 以维持 UART0 原波特率；UART6 波特率由板级代码固定设置，暂不提供动态改波特率功能。DDR、上游总线时钟和电源域继续沿用原引导固件。

## 加载与验证

沿用先前验证过的 Fastboot RAM 下载、CRC 校验与 `booti` 流程。新镜像入口为 0x40400000，使用原板级 DTB 地址 0x48300000。需要先释放 miniterm，再进入 U-Boot 的 `fastboot usb 0`，并确保下载设备接入 Ubuntu。

在现有 Ubuntu 环境，进入下载模式后：

```sh
cd /home/swl/openvela/work/rk3576-bringup
export PYTHONPATH="$PWD/host-tools/root/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
python3 ramboot_k7.py /home/swl/openvela/cmake_out/rk3576_gimbal_uart6 \
  --serial f71a9d152132db55 --log ../rk3576-gimbal/ramboot.log
```

该流程仅加载 RAM，不写 eMMC；断电后需要重新加载。已完成：启动日志显示 UART6 内部回环通过 → `ls /dev` 出现 ttyS1 → `gimbal info` / `frame` → 两次小幅目标发送 → 用户观察并确认云台运动。后续视觉跟踪、双轴性能与连续运行验证属于下一阶段。

## MCU 源码中的已知问题

现有 `E:\yuntai\1.人脸追踪\BSP\bsp_usart.c` 的 `DataDecode1()` 使用 `uart_rec_data[6]`，却接收 7 字节并访问下标 6，存在越界。应将该函数的缓存改为至少 7 字节并重新编译、烧录 MCU。此轮没有修改或烧录 MCU，也尚未确认板上正在运行的 MCU 固件是否包含同一问题。

## 校验与参考

固件 nuttx.bin：195312 字节。

SHA256：`baba87bc9d122cdfd991afe373cb237394bdf6a6928b0580ceee6391b56387b2`

- [KICKPI-K7 引脚与硬件](https://doc.kickpi.cn/Products/Introduction/KICKPI-K7/)
- [Rockchip RK3576 UART 设备树](https://github.com/rockchip-linux/kernel/blob/develop-6.1/arch/arm64/boot/dts/rockchip/rk3576.dtsi)
- [UART6 时钟定义](https://github.com/rockchip-linux/kernel/blob/develop-6.1/drivers/clk/rockchip/clk-rk3576.c)
- [引脚控制寄存器](https://github.com/rockchip-linux/kernel/blob/develop-6.1/drivers/pinctrl/pinctrl-rockchip.c)
