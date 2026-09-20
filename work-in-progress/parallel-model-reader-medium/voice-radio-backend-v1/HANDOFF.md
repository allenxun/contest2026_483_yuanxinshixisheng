# 真实无线后端接线候选：未进入正式源码/SDK/设备

本候选给出可审查的精确补丁 candidate.patch、新 C/INC 文件及更新的语音视图。不是生产默认 mock，也没有永久 firmware_order_proven=false 门禁。所有新增行为由默认关闭 CONFIG_EXAMPLES_K7RADIO_SHARED 控制，独立 RAM 镜像编译/板端验证须主会话完成。

## 接线与使用

candidate.patch 以 inputs.json 冻结的 app/k7radio 文件为准，包含正式文件精确差异和所有新增无线 C/INC/header；candidate/ 是改后供审查的正式文件副本。scan-cleanup-only.patch 是最初单点修正证据，不应覆盖最终完整补丁。不要混用旧头/对象：ws_done 新增 int error，wd_dispatch 有 scan 字段，全部对象/调用方必须重编。

启动顺序：启用新配置且支持 joinable pthread 的独立镜像 → bt-host 创建单一 RX 任务 → 显式 wifi-service-start。后者拒绝已在线/已有WPA资源/故障RX，原子占住服务启动权，实际发 STOP(6)、CLOSE(4)，等 RX 线程在关闭ACK之后的真实空队列边界，才 wd_init(...,true) 并创建永久 reaper 和 pump。启动失败保持禁止旁路，不允许第二次盲接管；本最小版本没有服务热重启/销毁，应回到受控重启恢复流程。

新的 k7_wifi_dispatch()/k7_wifi_scans() 在服务 ready 之前返回 NULL；在同 flat-build 进程内用其返回实例构造这里的 voicelink::SharedWifiPort。候选 Makefile 只编译无线 C 对象；C++ adapter 应加入 app/voicelink 自身构建、使用同一份 C 头，不另建一个 dispatcher。不能把 NULL 伪装成空列表或联网成功。无 ASR/TTS 改动。

BLE PROV_SCAN → ws_ble_begin/poll；BLE PROV_CONNECT → wd_ble_begin/poll，专用 prov_worker 有界等待，LPWORK 仍只通知，保留原 epoch 和加密/订阅边界。凭据复制后立即擦除 BLE req 密码。语音走相同 core 的固定 VOICE owner。新配置下所有原 wifi-* 改射频 CLI（包括旧 wifi-disconnect/auth/scan/join）在 main 入口拒绝，wifi-status只读保留；wifi-service-start例外。新配置下 prov_wifi_connect 不再自动断网接管。不要将旧 CLI 接回并保留“统一仲裁”结论。

## 实际执行/清理证据

- rb_enqueue 是有界单槽 submit：复制 job、票据和扫描类型；专用 reaper 启动 joinable operation pthread。operation 真实调用 fw_wifi_scan 或 fw_wifi_join_run，沿用 WPA/DHCP 实现，没有注入生产成功常量。g_wifi_operation 仍供原共享状态互斥，服务租约覆盖其释放后的维护期。
- reaper 对 operation pthread_join 成功后才记录 worker_joined。join失败不会当作退出；pump独立保持响应/held。线程创建失败是没有产生 operation 的明确路径，擦除凭据并发布失败；不是把普通函数 return 当任务退出。
- 每次真实 fw_wifi_command 的返回分别记录 OPEN尝试、SCAN、STOP ACK、CLOSE ACK、JOIN/UNJOIN。OPEN ACK失败仍可能有副作用，因此真实扫描函数仍走 CLOSE。OPEN后拿g_wifi_state失败也走 CLOSE。wait返回0却没有scan_done时先判超时再STOP，修正旧路径先CLOSE后才发现缺done。
- 当前唯一本机 RX 线程同步处理 report回调。在 fw_receive 真实读到 CCCR pending 无bit2、g_pending=0且FIFO指示相等时，rb_rx_idle记录空队列epoch/先前回调已返回。只有epoch严格晚于实际CLOSE ACK记录，才可形成清理凭据。仍有待处理slot时不会调用该钩子；不通过sleep推断空队列。
- scan完成事件分别携带 scan_done、stop_ok、close_ok、worker_exited、rx_quiescent、offline 和实际error；未开始SCAN时stop_ok代表无扫描需要STOP，不是发送成功。自然DONE可替代STOP。没有OPEN副作用的提交/操作前失败，也以“无接口待关”的明确路径释放。
- 新配置下 IP维护 worker 改为 joinable pthread（原默认构建保持kthread）。operation完成且实际 WPA completed、DHCP状态/IP/active 快照成立后，发布连接成功，radio保持OWNED；reaper随后真实join维护线程。IP cleanup分别记录keys/unjoin/close返回，只有清理和维护退出及RX屏障全部成立，才最终离线释放。status或密码接收不构造成功。
- stop回调只设置该job取消位/网络stop。现有阻塞操作并未改为可硬中断；扫描最多旧等待周期，关联/WPA/DHCP沿原等待。service超时可以先向客户报告，但必须held直到清理。现存IP失败等待done仍可能无限阻塞，独立pump不会因此释放资源。
- 清理/RX在2秒有界等候内未证明时发布非释放结果并保留后台槽/租约。本最小版本不自动重新OPEN、不强杀线程、没有故障后的retry/reset回收协议；需受控恢复。它不是正常路径永久held门禁。此限制需在目标故障处理中呈现，不能承诺任意错误都自动恢复。

## 官方依据及工程边界

输入来源是只读 E:/openvela/无线适配_2026-09-08/official-linux-20260320/source/...，不是运行SDK。官方 GPL-2.0 源完整保留在 input/official-* 供审计，未将其实现代码混入新的独立组件。

1. skwifi/skw_cfg80211.c:2598 scan_done 在 mutex 内摘除 scan_req、删除timer，aborted时发同步STOP后通知cfg80211；2632 abort_scan直接STOP→scan_done(false)，无scan generation标签、无“未来永不再有report”的形式化门禁。swt6621s_wifi对应2579/2613采用同一逻辑，已固定其源码哈希。
2. skw_msg.c:36完成事件调用scan_done；1928/1937命令发送等待ACK或退出条件。skw_msg.h明确CLOSE=4、STOP_SCAN=6。
3. skw_iface.c:873 teardown先scan_done(true)，再event_work_deinit，最后CLOSE。skw_work.h:77 event_work_deinit禁新事件→cancel_work_sync→purge队列。skw_rx.c:1941-1945将事件排入接口/全局队列，skw_work.c:370从队尾排入work。
4. 原生实现没有Linux那一层事件工作队列：单RX任务在槽解析内同步调用，因此“后续RX空边界”同时证明前面本机回调退出。选择依赖同版本驱动采用的DONE/STOP完成语义，再额外要求CLOSE ACK+本机RX空，而非人为设置无实现路径的firmware_order标志。

这是有来源支持的工程行为契约，不能证明固件缺陷绝不产生CLOSE后迟到旧report。硬件必须真实报告正确ACK/event；本地RX序列必须仍是单一同步分发。新SDK/固件版本、将RX改异步队列、或真机发现关闭后旧事件都必须重新审核。验证需记录STOP/DONE/CLOSE序号及空边界前后reports，连续BLE/voice扫描并交替取消；不要仅证明主机本地ticket过滤而宣称空口tag存在。

## 本批修正旧adapter两点

voice_wifi_adapter.cpp只在语音视图过滤隐藏/非法UTF8/控制字符SSID，保留可播报AP；不会改写SSID或混合BSSID。底层snapshot原字节与BLE base64列表保留全部记录。混合一条坏SSID+一条AP1的测试返回一个AP1且原snapshot仍2条。ws_done新增error，失败传实际错误，缺失错误时固定-5；提交回调拒绝默认-5，Timeout保留-110。旧冻结目录未改。

## 主机证据与仍待做

run_tests.py每个进程20秒限制，O0/O2均以Wall/Wextra/Werror/Wpedantic编译。真实最终 fw_wifi_scan抽取函数18项（普通完成、OPEN后锁失败仍CLOSE、超时STOP/CLOSE、CLOSE失败等）；实际 radio_backend.inc 使用真实pthread worker/reaper/pump，与明确mock射频/RX接缝执行正常扫描+连接失败，另测CLOSE失败、RX不排空、STOP失败维持held。更新adapter各4308检查（包含100轮真实双线程争用、SSID混合和error传播）。原始命令/输出 test-output.txt；这些不能作为真实RF扫描/DHCP/线程栈验收。

未运行SDK/NuttX编译，未验证完整 main/prov include组合在目标编译器下的警告、pthread配置/栈/优先级/flat符号导出、启动命令及初次无活动接口假设、BLE并发通知、真实扫描和真实IP移交、故障后复原。新任务栈16KiB、永久pump/reaper以及IP线程替换需要目标资源审查；radio主命令原栈4096，startup本地对象较小但BLE snapshot约3KiB需单独核算prov_worker8192。原无线代码若发生未处理mutex错误的更广泛后果未在本候选全量重构；不能声明上游所有失败路径已经安全。ROOT应先编译和静态审查，再在独立镜像做有限真实验证。
