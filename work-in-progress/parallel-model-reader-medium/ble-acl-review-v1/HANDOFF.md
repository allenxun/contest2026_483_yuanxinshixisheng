# BLE GAP成立但ACL_RX=0：只读定位

未找到可据现有证据确认的“WiFi在线把标准ACL误分到WiFi”bug；不提供猜测性协议/安全降级补丁。audio-route状态只证明GAP曾建立、软件ACL TX入队1次、成功解码并进入ready BT bridge的ACL RX计数0。encrypt_status=255是skw_bt.c连接时设置的0xff初值，不能解释为收到控制器0xff失败状态；encrypted=0与Windows pair FAILED不等于已看到板端SMP交互。

## 已定位的排除边界

- app/k7radio/k7radio_main.c:854-891先处理discard，再先分发BT端口2/5，后处理WiFi7/6。没有network_active条件把port5改为WiFi。单RX所有者为bt_rx_worker:1328→fw_receive(50)，WiFi fw_wifi_command在host模式等acksem而非另开fw_receive。正常在线路径未见第二个FIFO reader。
- skw_native.h:13-17的2/5/6/7与官方seekwaveplatform_lite/sdio/skw_sdio.h:126/129等对应；官方skw_platform_data.h:60 header.channel为完整8bit。skw_sdio_rx.c:1305直接取header.channel，没有高位掩码。因此目前没有依据对channel任意&0x7f/0x0f；0xff是filler而非EOF，正式代码已有区分。
- skw_bt.c:159-162先acl_rx++，到187才做upper frame容量限制，191才交bt_netdev_receive。ACL_RX=0不能优先归因于ATT权限、SMP安全策略或upper buffer太小；这些发生在计数之后。bridge未opened/ready失败仍可能在计数之前退出。
- skw_packet.c:80-96按ACL 4字节header和16位LE body长度解析，CMD event与DATA ACL分别校验H4类型；12字节逻辑前缀与官方skw_sdio_rx.c:1125去前缀相符。官方BT callback按H4类型分派，主机候选更严格限制port/H4组合和最多3字节零padding。
- 实际artifacts/audio-route-20260910/.config已冻结：CNTRL_HOST_FLOW_DISABLE=y、BUFFER_PREALLOC=8、IOB_BUFSIZE=256。bt_hcicore.c:1413的host-buffer广告在这个配置下跳过，0x0c31发送0关闭controller→host ACL credit限制，并核实际HCI完成status。不能将“广告0个ACL缓存”当本镜像已证实原因。

## 优先检验的三个假设（均未证实）

1. **软件ACL已排队，但没有真正交给控制器或缺逻辑ACK。** skw_bt.c:62的acl_tx在lower->send成功后递增；lower只复制到g_bt_queue，实际fw_packet在k7radio_main.c:1311，随后才等logical ACK。先记录同一短连接窗口的g_bt_count、pending/channel、host_tx、host_ack、worker_fault及ACL入队/提交时间。若TX差值没有增加，查调度/队列；若提交增加但ACK不增，查控制器/SDIO逻辑流控。bt_lower_ack当前忽略seq，是已知局限，不能未经匹配证据就断言它解释当前首个ACL失败。
2. **有port5槽，但在bridge计数前被严格解析或ready检查拒绝。** 最小诊断是每端口slot计数、port5长度/H4类型、decoder返回分类、bt.opened/worker_fault；只记录头长度/类型和计数，不记录SMP密钥/用户内容。nonzero alignment tail、port2上的H4 ACL、截短ACL均会被现有codec拒绝。官方低层callback不做同样的零padding检查，但其上层接受性未在本审查证明。需要实际失败slot才决定更改；不凭合成用例放宽解析。现代码decode失败会返回到RX worker并令共享fault=true，故若同一时段持续WiFi收发且fault=0，该假设应下调。
3. **控制器没有发回ACL，或共享RX/TX处理时延令中央端放弃。** GAP只验证event端口，不证明ACL空口/控制器传输。若原始port5计数始终0且TX提交/ACK均正常，再对照0x0c31的真实complete status、Number Of Completed Packets事件、单RX循环最大间隔与WiFi流量。Windows pair FAILED及权限提升本身不能区分控制器未回、中央端未发送、旧bond状态或调度问题；没有SMP RX证据前不修改IO能力、加密/鉴权门禁。

一次最小窗口即可先区分：连接前后host-status/ble-status，加只统计端口与TX队列阶段的短期有界诊断。记录是否WiFi同时在线以及相同镜像hash；不要拿前一轮网关5/5当故障发生后的RX线程无fault证明。这里仅给主会话可执行检查，不访问设备。

## 主机与交付

skw_packet.c/skw_native.h逐字复制正式源码；O0/O2严格Wall/Wextra/Werror/Wpedantic主机测试验证合法port5 ACL可解码、非零tail/错误H4-port/高channel/截短ACL拒绝及0xff discard。输入都是合成字节，不是抓获的失败ACL，不构成根因复现。命令与原始输出在test-output.txt，每进程15秒。

inputs.json包含正式radio/BT glue、NuttX BT core/buffer、实际audio-route配置/状态证据与官方Seekwave源码哈希。未读私密配置或凭据日志；没有SDK/设备/正式源码/中央日志修改，也没有降低配对安全要求。
