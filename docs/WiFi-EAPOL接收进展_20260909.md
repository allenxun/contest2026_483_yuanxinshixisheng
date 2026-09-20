# Wi-Fi EAPOL 接收链路进展

本轮在统一项目 `app/k7radio/` 继续开发，版本标记 `eapol-rx-20260909`。尚未上板；最后无线真机验证仍为 id36。本轮没有启动云台、刷写 eMMC 或改变前端联网成功条件。

## 本轮实现

- 将此前待接入的 EAPOL 编解码头移入实际应用目录，Wi-Fi 数据接收分支使用完整 SDIO slot 解析，避免 PN reuse 模式下误去掉四字节头。
- 从已经验证过长度、芯片类型的 GET_INFO 回复偏移 90 读取 private capabilities 的 bit 2，确定描述符布局。依据官方 Linux SDK 的 packed `skw_chip_info`，而非根据模块商品名称猜测。
- 新增四槽、每槽最多 1024 字节的静态接收队列。按本机 MAC、目标 BSSID、instance 和 peer 过滤；复制报文后才返回共用 RX 线程。该路径不发送命令、不等待固件 ACK，也不动态分配内存。
- 在发送 ASSOC 前绑定并开启接收队列，捕获可能立即到达的 EAPOL。关联探针的观察窗口仍为 1.5 秒。结束时输出接收/拒绝/溢出计数并清空队列；不再打印原始数据帧前缀。
- 提供出队接口及断开清理，供后续 WPA 工作线程调用。当前探针只观察和计数，尚未调用 WPA 状态机；接收通过仅表示报文结构和来源通过运输层检查，不表示 MIC、重放检查或握手成功。

## 验证结果

`tests/wifi/test_eapol_codec.c` 与 `test_eapol_queue.c` 在 Ubuntu GCC `-Wall -Wextra -Werror`、ASan、UBSan 下通过。覆盖容量限制、FIFO 环绕、共享缓冲区复用后副本完整、所有截断长度、错误 peer/地址、断开清空，以及原编解码的 20,000 个畸形输入。

测试主体是合成报文；其中编解码测试仅描述符前缀来源于旧 id36 实测。没有把合成测试写成真实 WPA 握手。

统一 openvela 编译成功，产物位于 `artifacts/eapol-rx-20260909/`。新 `nuttx.bin` 为 **1,915,896 字节**，SHA-256：

```text
97f4accb36cae6cab6a171ee8e6f2d91fb02c03d7e46588a12f65cae2099eb48
```

原始测试输出、编译状态及本轮全部 k7radio 源文件哈希在 `evidence/build/eapol-rx-20260909/verification.json`，构建输出在同目录 `build.log`。复现入口为 `tools/verify_eapol_rx_vm.py`，固定指向已配置的 VM SDK；不执行硬件操作。

`evidence/source-files.json`、`accepted-source-comparison.json` 及旧 `project-verification.json` 是首次统一版本快照，不是本轮源码的重新验收。本轮有意修改 `k7radio_main.c` 和 `wifi_assoc_probe.inc`；本轮源码状态以新验证文件和开发清单为准。旧镜像与历史证据保留。

## 后续必需工作

1. 在独立 WPA 工作上下文消费队列，接入可信随机源、定时器和上游 WPA 状态机。
2. 实现 EAPOL 命令 15 发送及 ACK 错误传递、PTK/GTK 安装和失败清除。
3. 接通 netdev 数据收发及 DHCP，再验证真实 IP 通信和 BLE/Wi-Fi 并行运行。

前端 `connect` 仍应返回现有 `not_ready`，不可显示联网成功。本轮不需要前端修改协议，也没有将用户密码放入代码、VM 或公开日志。

## AI 日志归属

真实开发记录继续写入本仓 `logs/maomaojiang01/2026-09-08/codex__01a07ed4-3f0d-7450-8bb1-bb756849cb4e.jsonl`，与已有会话在同一 manifest 中合并。官方校验输出在 `evidence/official-log-validation.txt`。日志按真实消息导出和脱敏，不补造历史提交或成功测试。
